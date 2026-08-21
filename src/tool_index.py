"""
RAG-based tool selection for agent mode.

Instead of injecting all tool descriptions into the system prompt,
embed them in a ChromaDB collection and retrieve only the top-K
relevant ones per user message.
"""

import asyncio
import hashlib
import logging
import re
import threading
import time
from typing import Dict, List, Optional, Set

from src.embedding_lanes import (
    LANE_CUSTOM,
    LANE_FASTEMBED,
    build_embedding_lanes,
    dedupe_results,
    migrate_legacy_collection,
)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

logger = logging.getLogger(__name__)

# Tools that are ALWAYS included regardless of retrieval results.
# Keep this deliberately tiny. Domain tools (web, documents, email,
# cookbook/model serving, files, settings, etc.) are injected by retrieval or
# keyword intent so a trivial agent prompt like "test" does not carry every
# domain's schemas and rules.
ALWAYS_AVAILABLE = frozenset({
    # Memory is ambient — "remember this" can follow any message regardless
    # of topic. Without this, RAG drops it and the agent falls back to
    # app_api /api/memory/add which fails with 422 on first attempt.
    "manage_memory",
    # Ask the user a multiple-choice question for a decision/clarification.
    # Always reachable so the agent can pause and ask at any point.
    "ask_user",
    # Write back to the active plan (tick steps done / revise) during execution.
    "update_plan",
})

# Tools that the Personal Assistant always has access to during scheduled
# check-ins and proactive tasks, in addition to RAG-selected tools.
ASSISTANT_ALWAYS_AVAILABLE = frozenset({
    "list_email_accounts", "list_emails", "read_email", "send_email", "reply_to_email",
    "bulk_email", "archive_email", "delete_email", "mark_email_read",
    "manage_calendar", "manage_notes", "manage_tasks",
    "manage_memory", "web_search", "read_file",
    "create_document", "update_document",
    "resolve_contact", "search_chats",
    "api_call",  # For Miniflux/Gitea/Linkding/etc. integrations
    # Core UI control (toggles, open panels, switch model/mode, themes).
    # Always available so vague follow-ups ("now make it playful", "make it
    # darker") that don't repeat a theme/UI keyword still keep the tool in
    # reach — without it the model narrates instead of acting.
    "ui_control",
})

# Scheduled Ras Morning Brief allowlist (app-driven gather). Shared with chat
# operator-brief routing so cron and conversational briefs cannot diverge.
MORNING_BRIEF_TOOLS = frozenset({
    "manage_notes",
    "manage_calendar",
    "app_api",
    "create_document",
    "update_document",
    "manage_documents",
    "mcp__email__list_emails",
    "list_emails",
})

# Chat "Morning Brief" / focus / consensus: scheduled gather pack plus skill
# load and a news scan. Must remain a strict superset of ALWAYS_AVAILABLE.
OPERATOR_BRIEF_TOOLS = MORNING_BRIEF_TOOLS | frozenset({
    "manage_skills",
    "web_search",
})

COLLECTION_NAME = "odysseus_tool_index"

# ── Tool description registry ──
# Each tool gets a searchable description that helps retrieval.
# These are richer than the system prompt one-liners — they're for embedding.
BUILTIN_TOOL_DESCRIPTIONS: Dict[str, str] = {
    "bash": "Run shell commands on the server. Install packages, check files, git operations, system info, and process management. Do not use for web lookup/search; use web_search or web_fetch when web tools are available.",
    "python": "Execute Python code for computation, data processing, math, scripting, and parsing. Not for writing code for the user. Do not use for web lookup/search; use web_search or web_fetch when web tools are available.",
    "web_search": "Quick single web lookup for a fact, current event, latest/current information, or doc mid-task. Use this instead of bash/curl/python/requests for web searches. NOT for 'research X' / 'do research on X' requests — those are deep-research jobs (use trigger_research). web_search = one query; trigger_research = a full researched report in the sidebar.",
    "web_fetch": "Fetch and read the text content of a specific URL/website the user names (e.g. 'check example.com', 'open this link'). Use when you have a concrete URL; for open-ended lookups use web_search instead.",
    "read_file": "Read a file from disk and return its contents. View source code, config files, logs. Supports an optional line range (offset/limit) for large files.",
    "grep": "Search file CONTENTS for a regex across a directory tree (ripgrep-backed, honours .gitignore). Returns file:line:match. Use to find where code/symbols/strings live — prefer over bash grep.",
    "glob": "Find FILES by glob pattern (e.g. '**/*.py'), newest first. Use to locate files by name/extension — prefer over bash find/ls.",
    "ls": "List a directory's entries (folders then files with sizes). Use to see what's in a folder — prefer over bash ls.",
    "write_file": "Write/create or fully rewrite a file ON DISK (source code, configs, project files). Use for new files or full rewrites — NOT create_document (editor panel) and NOT a bash heredoc.",
    "edit_file": "Edit an existing file ON DISK by exact string replacement (fix a bug, change a function). Shows a diff. The tool for changing files on disk — NOT edit_document (editor panel) and NOT bash sed/heredoc.",
    "create_document": "Create a new document in the editor panel. For code, articles, text content longer than 15 lines, unless an already-open document/email draft is the obvious target. If an email compose draft is open, edit that draft instead of creating another document.",
    "edit_document": "Preferred tool for editing an existing document — targeted find-and-replace. Use for any small change: add a function, fix a bug, tweak a section, rename things.",
    "update_document": "Replace the entire active document content. ONLY for full rewrites (>50% changed). Do not use for small edits — use edit_document instead.",
    "suggest_document": "Suggest changes to the active document with explanations. For code review, proofreading, feedback requests.",
    "generate_image": "Generate an AI image from a text prompt. Specify model, size, and quality. Art, illustrations, photos.",
    "chat_with_model": "Send a message to a different AI model. Compare responses, get specialized help, delegate tasks.",
    "ask_teacher": "Ask a more capable model for help with a difficult problem. Escalate complex tasks.",
    "pipeline": "Run a multi-step AI pipeline with multiple models. Chain tasks together in sequence.",
    "list_models": "List all available AI models and their endpoints.",
    "manage_session": "Chat management: rename, archive, delete, or fork chats (the UI calls these 'chats'; internally 'sessions'). Use for 'rename my chats', 'rename this chat', 'archive/delete a chat'.",
    "manage_memory": "Memory management: list, add, edit, delete, or search persistent memories.",
    "manage_skills": "Skill management: add, update, publish, or search reusable skills/presets.",
    "manage_tasks": "Manage SCHEDULED BACKGROUND AI JOBS (recurring automations in the Tasks panel) — NOT the user's todo list. An empty list here does NOT mean the user has no todos; call manage_notes action=list for user todos/checklists. Use for: list, create, edit, delete, pause, resume, or run cron tasks.",
    "manage_endpoints": "Endpoint management: list, add, delete, enable, or disable model API endpoints.",
    "manage_mcp": "MCP server management: list, add, delete, reconnect servers, or list available tools.",
    "manage_webhooks": "Webhook management: list, add, delete, enable, or disable webhooks.",
    "manage_tokens": "API token management: list, create, or delete API access tokens.",
    "manage_documents": "List, read, delete, or tidy documents in the editor panel. action='list' returns clickable rows (most-recent first) so the user can open any doc by clicking. action='read' (aka view/open/get) with document_id returns the content. action='delete' with document_id removes a doc (only way to delete). Use this for ANY 'show/read/list/open my documents/docs/files/notes' request — never shell or curl.",
    "manage_research": "List, read/open, or delete saved DEEP RESEARCH results from the Library. action='list' returns clickable [query](#research-<id>) rows (most-recent first). action='read' (aka open/view/get) with id returns the report + sources. action='delete' with id removes it. Use this for ANY 'open/read/find/delete my research / that report / the research on X' request. NOTE: this is for EXISTING research; to START new research use trigger_research.",
    "process_job_application": "Job search pipeline: ingest postings, evaluate rubric gate (4.0+ proceeds), dispatch Cursor tailoring handoffs, list/status jobs, build Handshake apply packages, mark applied, or archive (user decline/pause — terminal archived, no follow-up). NEVER auto-submits to Handshake. Use archive — not mark_applied — when clearing stale leads.",
    "manage_settings": "Change ANY real app setting (the ones the Settings panel writes) so the user never has to open it: TTS voice/provider/speed, STT, search engine + result count, default/teacher/task/utility/vision/image/research models, image quality, reminder channel (browser/email/ntfy), agent timeout/tool-call budget, and more. action=set with key (friendly aliases ok: voice, 'search engine', 'default model', 'teacher model', 'image quality', 'reminder channel'...) + value; get/list/reset too. Also toggles tools on/off (disable_tool/enable_tool/list_tools). Secrets/API keys are read-only. Use for any 'change my…/set my…/use X for…/turn on…' preference request.",
    "create_session": "Create a new chat with a name and model.",
    "list_sessions": "List all chats with their metadata (the UI calls these 'chats'). Use for 'list my chats', 'rename all my chats' (list first, then manage_session to rename each).",
    "send_to_session": "Send a message to another chat. Cross-chat communication.",
    "search_chats": "Search past session transcripts across chats.",
    "ask_user": "Ask the user a multiple-choice question to get a decision or clarification. Use this when the task is genuinely ambiguous and the answer changes what you do next — pick between approaches, confirm an assumption, choose among options — instead of guessing. Provide a clear `question` and 2-6 `options` (each with a short `label`, optional `description`). Calling this ENDS your turn: the user sees clickable buttons and their choice arrives as your next message. Don't use it for things you can decide from context or sensible defaults, or for irreversible-action confirmation if a dedicated flow exists.",
    "update_plan": "Write back to the ACTIVE PLAN while executing an approved plan: mark steps done or revise them. After finishing a step call this with the full checklist and that step marked done; when the user asks to change the plan call it with the revised checklist. Always pass the COMPLETE markdown checklist (`- [ ]` / `- [x]`), not a diff. The user's docked plan window updates live. No effect when there is no active plan.",
    "ui_control": "Control the UI and toggle tools on/off. Use this to turn off / turn on / disable / enable individual tools and features: shell (bash), search (web), research, browser, documents, incognito. Open panels (documents library, gallery, email inbox, sessions, notes, memories/brain, skills, settings, cookbook, cmd-center/vault) via `open_panel <name>`. Use `open_email_reply <uid> <folder> reply` to open an email reply draft document without sending. Also switches between chat/agent modes, changes the current model, and applies/creates themes.",
    "list_email_accounts": "List configured email accounts and default status. Use before reading or sending mail when the user mentions Gmail, work mail, custom domain mail, another mailbox, or asks to compare/check multiple inboxes.",
    "list_emails": "List emails for a folder/account, newest first, including read messages by default. Shows subject, sender, date, UID, account, and AI summary. Check inbox, find emails needing replies. Supports account from list_email_accounts for Gmail/work/custom mailboxes. For last/latest/newest email, use max_results=1 and unread_only=false.",
    "read_email": "Read the full content of a specific email by UID or Message-ID. View email body, check details. Supports account from list_email_accounts when the UID belongs to a non-default mailbox.",
    "send_email": "Send a new email via SMTP. Provide recipient, subject, body, and optional account from list_email_accounts. For replying to a thread use reply_to_email instead.",
    "reply_to_email": "SEND a reply email immediately by UID. Do not use for open/start reply draft requests; use ui_control open_email_reply for those. For follow-up 'reply ...' send requests, use the exact UID and account from latest read_email/list_emails output; never invent UID 1. Threads automatically with In-Reply-To/References, prefixes Re:, marks original as Answered.",
    "archive_email": "Move an email out of the inbox into the Archive folder. Use after handling messages you want to keep but get out of the way.",
    "delete_email": "Delete an email — moves to Trash by default, or expunges permanently with permanent=true.",
    "mark_email_read": "Mark an email as read or unread by toggling the \\Seen flag.",
    "bulk_email": "Perform one action on many emails at once. Use for delete all those, archive these, mark all read, move spam to junk. Takes explicit UIDs from list_emails or all_unread=true. Always pass account for Gmail/work/custom mailbox results.",
    "resolve_contact": "Look up a contact's email address by name. Searches CardDAV address book and sent email history. Use when the user says 'message [name]', 'email [name]', or 'send to [name]' without an email address.",
    "manage_contact": "Create, update, delete, or list CardDAV contacts. Use to save a new contact, change an existing one's email/phone, or remove one. Action=list returns uids needed for update/delete. Use when the user says 'save this contact', 'add [name] to contacts', 'update [name]'s email', 'delete [name] from contacts'. Do not use for user identity facts like 'my name is <name>'; those are memory.",
    "manage_notes": "List, create, and manage the user's notes, todos, checklists, and reminders (Odysseus Notes panel). ALWAYS call action=list when the user asks to see/analyze/categorize their todo list — this is the canonical source of user todos. NEVER use manage_tasks or Notion for user todos. Accepts natural-language `due_date` like 'tomorrow at 9am' or '11pm today' (parsed in the USER'S timezone). The due_date IS the reminder — it fires a notification at that time, so do NOT also create a calendar event for the same reminder. Set colors, labels, pin, archive. Do NOT use manage_memory for note content.",
    "manage_calendar": "Calendar event management: list, create, update, delete. Each event can carry a tag/category (event_type — work/personal/health/travel/meal/social/admin/other) and importance (low/normal/high/critical). Resolve today/tomorrow using the Current date and time context, then use ISO datetimes in the user's local wall time; supports all-day events. For event reminders/alarms, pass reminder_minutes; this creates the Notes reminder, so do not also call manage_notes for the same reminder.",
    "download_model": "Download a HuggingFace model to a local or remote server. Specify repo_id (e.g. 'Qwen/Qwen3-8B'), optional server host, and optional include filter for specific files.",
    "serve_model": "Start serving a model with vLLM, SGLang, llama.cpp, Ollama, or Diffusers. cmd MUST start with the binary directly — e.g. `vllm serve /mnt/HADES/models/Qwen3.5-397B-A17B-AWQ --port 8003 --tensor-parallel-size 8 …`. NEVER prefix with `cd …`, `source …`, or chain with `&&`/`||` — those get rejected by the validator. The venv activation (env_prefix) and CUDA env are added automatically from the target host's saved settings. For image/inpainting/diffusion use python3 scripts/diffusion_server.py --model <repo> --port 8100. After launch, call list_served_models for readiness/errors and retry suggestions. If serve_model fails with 'Invalid characters in cmd', simplify to the bare binary + args.",
    "list_served_models": "List currently running model servers in the Cookbook — shows status (loading, ready, idle, error), model name, port, throughput, and serve failure diagnosis/retry suggestions. Use when the user asks 'what's running', 'show my cookbook', 'which models are up', 'what's serving'.",
    "stop_served_model": "Stop a running model server in the Cookbook by session ID or model name. Use when the user says 'kill my cookbook', 'stop the model', 'kill the serve', 'shut down vLLM', 'cancel the running model'.",
    "tail_serve_output": "Read the actual tmux stderr/traceback of a cookbook serve/download task. Use to debug WHY a task is `crashed`/`error` (compute_89 nvcc mismatch, OOM, missing kernels, wrong attention backend, etc.) so you can call serve_model with adjusted flags. Pass session_id from list_served_models; tail defaults to 300, bump if the error references 'see root cause above'.",
    "list_downloads": "List in-progress HuggingFace model downloads in the Cookbook. Shows model name, phase, percent, session ID. Use for 'what's downloading', 'show my downloads', 'check download progress'.",
    "cancel_download": "Cancel an in-progress model download by tmux session ID. Use for 'cancel the download', 'stop downloading X', 'kill the download'. Call list_downloads first to get the session_id.",
    "search_hf_models": "Search HuggingFace for models matching a query (e.g. 'qwen 8B', 'flux', 'llama-3 instruct'). Returns ranked repo IDs with sizes and download counts. Use for 'find a model', 'search huggingface for X', 'what models are there for Y'.",
    "list_cached_models": "List models already cached on disk locally or on a remote host. Accepts friendly Cookbook server names like ajax. Use for 'what models do I have', 'show cached models', 'is X downloaded', 'list my models'. Avoids re-downloading.",
    "list_serve_presets": "List saved Cookbook serve presets (templates with model+host+port+cmd). Always call this BEFORE serve_model when the user asks to launch a known model — they probably have a preset for it from the UI.",
    "serve_preset": "Launch a saved Cookbook serve preset by name. Reuses the exact tmux command + host the user already saved. Use for 'run stable diffusion 3.5', 'serve vllm-qwen', 'start the inpaint model' — preset-name matches the user's UI labels.",
    "adopt_served_model": "Register an existing tmux model server (one started manually or outside the cookbook flow) into Cookbook tracking AND add it as a chat endpoint. Use when the user (or a previous turn) launched something via ssh+tmux and now wants it visible in the UI, stoppable via stop_served_model, and usable in the model picker.",
    "list_cookbook_servers": "List the cookbook's configured servers (remote GPU boxes + local) and which is the current default. Use this BEFORE download_model/serve_model when the user didn't name a host — to decide where to run, or to ask the user which server when ambiguous. Downloads/serves default to the cookbook's selected server, NOT localhost.",
    "app_api": "Generic loopback to allowed Odysseus internal endpoints. Use this when the user wants something the UI can do but there's no named tool for it. Covers calendar, gallery, library/documents, memory, notes, tasks, settings, research, compare, cookbook GPUs/state — allowed UI buttons hit /api/* endpoints and you can hit them too. Sensitive auth/user/admin/shell paths and host-control Cookbook mutation routes are blocked; do NOT use app_api for shell commands, package installs, engine rebuilds, or PID signalling. Use named command tooling for shell commands. action='endpoints' with filter=<keyword> lists available endpoints. action='call' takes method+path+body. Hits same routes the UI uses — auth flows free. NOTE: themes are NOT an API endpoint — use the ui_control tool (create_theme / set_theme), not app_api. SESSIONS/CHATS: do NOT use app_api for these — GET /api/sessions returns EMPTY for tool calls (it's owner-filtered and tool calls authenticate as a different identity). EMAIL ACCOUNTS: do NOT use /api/email/accounts via app_api; use list_email_accounts, list_emails, and read_email instead. To list/rename/archive/delete/fork chats use the list_sessions and manage_session tools instead. DISABLED (Docker): do NOT use app_api POST /api/clicky/start to launch Clicky — container cannot spawn Windows WPF; host script deploy/scripts/start-clicky.ps1 instead.",
    "edit_image": "Edit an image in the gallery: upscale (increase resolution), remove background (rembg), inpaint (fill selected area), or harmonize (blend edits). Specify image ID and action.",
    "trigger_research": "Start a deep research job on any topic — appears in the Deep Research sidebar, streams progress, produces a detailed report. Use for 'research X', 'look into Y', 'do deep research on Z', 'investigate'. NOT a scheduled task — it runs now and surfaces in the sidebar.",
    "transcribe_video": "Get the FULL transcript of a video from its URL — YouTube or any yt-dlp-supported site. Tries YouTube captions first, then the Aether local server (yt-dlp + Whisper STT) for caption-less videos. Use for 'transcribe this video', 'get the transcript of this YouTube link', 'summarize/brief this video', 'CEO brief of this talk'. Returns full plain text plus title/channel/duration; can save the transcript as a document.",
    "screen_look": "See what is on the user's screen RIGHT NOW or in the last few minutes via Screenpipe OCR. Use for 'what am I looking at', 'what's on my screen', 'read the error on my screen', 'what app am I in', 'find <text> on my screen'. Optional SHORT keyword query (1-4 words — never the full spoken sentence) + minutes lookback (max 120). For 'a few minutes ago' prefer this over screen_recall. Read-only; not for past days (use screen_recall).",
    "screen_recall": "Search the user's INDEXED screen history semantically (PixelRAG visual tiles + agent memories + notes) — 'when did I see that stripe dashboard', 'find the article I had open yesterday'. If visual_results are empty, immediately fall back to screen_look with minutes + a short keyword. For the current screen or last few minutes use screen_look instead.",
    "spec_trace": "Read UI element context the user captured with the SpecTracer browser extension — DOM hierarchy, CSS selector, classes, position, console errors and events for a specific element they picked while developing. Use for 'the element I just grabbed/traced/captured/inspected', 'look at that button I picked', 'fix the element in my trace'. action=latest/list/get.",
    "desktop_act": "Control the user's desktop through the Clicky worker: move/click/double_click/drag the mouse at coordinates or at visible on-screen text (target_text, resolved via screen OCR), speak text aloud. Use for 'click the submit button', 'click on X', 'move the mouse to', 'double click'. Consent-gated per session — ask the user first when it returns consent_required. Pair with screen_look to see the screen before acting.",
    "browser_act": "Control the user's running Chrome via DevTools (Path B, :9222): list tabs, snapshot interactive elements, navigate, click/type by selector, or evaluate JS. Use for 'open <url> in my browser', 'what tabs do I have open', 'click the login button on the page', 'fill in the form', 'what's on this page' (structured, not OCR). Reads are free; navigate/click/type/evaluate are consent-gated. For Handshake/Comet or screenshot→click_at_xy, use external browser-harness CLI at BU_CDP_URL=http://127.0.0.1:9333 instead (Path A) — not this tool, not Docker MCP Playwright. See docs/grounded-build-spec-browser-harness-handoff.md.",
    "operator_research": "Fan out ONE web query across TinyFish + Perplexity + Firecrawl at once and return merged, deduplicated, ranked results with per-provider attribution. Use for 'search everywhere for X', 'cross-check X across engines', 'give me a broad web sweep of X' — broader than web_search but NOT the deep-research sidebar (trigger_research). Heavier than web_search (multiple APIs); prefer web_search for a single quick fact.",
}


class ToolIndex:
    """ChromaDB-backed tool index for RAG-based tool selection."""

    def __init__(self):
        self._lanes = build_embedding_lanes(COLLECTION_NAME)
        if not self._lanes:
            raise RuntimeError("No embedding lanes available")
        self._embedder = self._lanes[0].client
        self._collection = next(
            (lane.collection for lane in self._lanes if lane.name == LANE_FASTEMBED),
            self._lanes[0].collection,
        )
        migrate_legacy_collection(COLLECTION_NAME, self._lanes)
        self._fingerprint = ""
        self._mcp_generation = -1
        self._healthy = True
        logger.info("ToolIndex initialized (lanes=%s)", [lane.name for lane in self._lanes])

    @property
    def healthy(self):
        return self._healthy

    def _embed(self, texts: List[str]) -> List[List[float]]:
        if not self._lanes:
            return []
        vecs = self._lanes[0].encode(texts)
        if np is not None:
            return np.array(vecs, dtype=np.float32).tolist()
        return [list(v) for v in vecs]

    def index_builtin_tools(self):
        """Index all built-in tool descriptions."""
        docs = []
        ids = []
        metadatas = []
        for name, desc in BUILTIN_TOOL_DESCRIPTIONS.items():
            doc_text = f"Tool: {name}\n{desc}"
            docs.append(doc_text)
            ids.append(f"builtin_{name}")
            metadatas.append({"tool_name": name, "tool_type": "builtin"})

        if not docs:
            return

        # Drop any stale builtin_* entries that aren't in the current
        # registry (e.g. removed tools like the old vault_* set).
        # Without this, upsert leaves them in place and RAG keeps
        # surfacing tools that no longer exist.
        indexed = False
        encoded = False
        wanted = set(ids)
        for lane in self._lanes:
            try:
                existing = lane.collection.get(where={"tool_type": "builtin"})
                existing_ids = (existing or {}).get("ids") or []
                stale = [i for i in existing_ids if i not in wanted]
                if stale:
                    lane.collection.delete(ids=stale)
                    logger.info(f"Pruned {len(stale)} stale builtin tool entries from {lane.name} index")
                remaining = set(existing_ids) - set(stale)
                if remaining >= wanted:
                    indexed = True
                    continue
            except Exception as e:
                logger.debug(f"Stale-pruning skipped for {lane.name}: {e}")

            try:
                lane.collection.upsert(
                    ids=ids,
                    documents=docs,
                    embeddings=lane.encode(docs),
                    metadatas=metadatas,
                )
                indexed = True
                encoded = True
            except Exception as e:
                logger.warning("Builtin tool indexing failed in %s lane: %s", lane.name, e)
        if not indexed:
            self._healthy = False
            raise RuntimeError("Builtin tool indexing failed in all embedding lanes")
        self._fingerprint = hashlib.sha256(
            ",".join(sorted(BUILTIN_TOOL_DESCRIPTIONS.keys())).encode()
        ).hexdigest()
        if encoded:
            logger.info(f"Indexed {len(docs)} built-in tools")
        else:
            logger.info(f"Indexed {len(docs)} built-in tools (already present)")

    def index_mcp_tools(self, mcp_mgr, disabled_map: Optional[Dict] = None):
        """Index MCP tool descriptions. Call after MCP servers connect/disconnect."""
        if not mcp_mgr:
            return

        # Get current MCP generation to avoid redundant reindexing
        gen = getattr(mcp_mgr, '_generation', 0)
        if gen == self._mcp_generation:
            return

        # Remove old MCP entries
        for lane in self._lanes:
            try:
                existing = lane.collection.get(where={"tool_type": "mcp"})
                if existing and existing["ids"]:
                    lane.collection.delete(ids=existing["ids"])
            except Exception:
                pass

        # Get current MCP tools
        try:
            all_tools = mcp_mgr.get_tool_descriptions_for_prompt(disabled_map or {})
        except Exception:
            all_tools = ""

        if not all_tools:
            self._mcp_generation = gen
            return

        # Parse MCP tool descriptions from the prompt text
        docs = []
        ids = []
        metadatas = []
        current_server = ""
        for line in all_tools.strip().split("\n"):
            line = line.strip()
            # Track which server section we're in (for context in descriptions)
            if line.startswith("**") and line.endswith(":**"):
                current_server = line.strip("*: ")
            elif line.startswith("- ") and ":" in line:
                # Format: "- tool_name: description"
                name_desc = line[2:].split(":", 1)
                if len(name_desc) == 2:
                    name = name_desc[0].strip()
                    desc = name_desc[1].strip()
                    # Include server identity in the indexed text so RAG can
                    # distinguish "list_emails for server-a" from "list_emails for server-b"
                    server_ctx = f" (server: {current_server})" if current_server else ""
                    doc_text = f"Tool: {name}{server_ctx}\n{desc}"
                    docs.append(doc_text)
                    ids.append(f"mcp_{name}")
                    metadatas.append({"tool_name": name, "tool_type": "mcp"})

        if not docs:
            self._mcp_generation = gen
            return

        indexed = False
        for lane in self._lanes:
            try:
                lane.collection.upsert(
                    ids=ids,
                    documents=docs,
                    embeddings=lane.encode(docs),
                    metadatas=metadatas,
                )
                indexed = True
            except Exception as e:
                logger.warning("MCP tool indexing failed in %s lane: %s", lane.name, e)
        if not indexed:
            logger.warning("MCP tool indexing failed in all embedding lanes")
            return
        self._mcp_generation = gen
        logger.info(f"Indexed {len(docs)} MCP tools")

    def retrieve(self, query: str, k: int = 8) -> List[str]:
        """Retrieve the top-K most relevant tool names for a query."""
        rows = []
        lane_priority = {LANE_CUSTOM: 0, LANE_FASTEMBED: 1}
        for lane in self._lanes:
            try:
                count = lane.count()
                if count == 0:
                    continue
                results = lane.collection.query(
                    query_embeddings=lane.encode([query]),
                    n_results=min(k, count),
                    include=["metadatas", "distances"],
                )
                if not results or not results.get("metadatas"):
                    continue
                distances = results.get("distances") or []
                for list_idx, meta_list in enumerate(results["metadatas"]):
                    distance_list = distances[list_idx] if list_idx < len(distances) else []
                    for idx, meta in enumerate(meta_list):
                        name = meta.get("tool_name", "")
                        if name:
                            distance = distance_list[idx] if idx < len(distance_list) else 1.0
                            rows.append({
                                "tool_name": name,
                                "score": round(1.0 - distance, 4),
                                "embedding_lane": lane.name,
                            })
            except Exception as e:
                logger.warning("Tool retrieval failed in %s lane: %s", lane.name, e)
        rows.sort(key=lambda row: (-row["score"], lane_priority.get(row["embedding_lane"], 99)))
        return [row["tool_name"] for row in dedupe_results(rows, id_key="tool_name", limit=k)]

    # Structural recurring-schedule intent. Typo-resilient (matches "every dya"
    # via "every <word>"), and catches bare clock times ("at 7:30 am", "7am").
    # Used in addition to the literal keyword hints below.
    _SCHEDULE_RE = re.compile(
        r"\bevery\s+\w+"                                       # every day / dya / morning / monday / 2 hours
        r"|\b(?:daily|nightly|hourly|weekly|monthly)\b"
        r"|\beach\s+(?:day|morning|night|week|hour|evening)\b"
        r"|\bat\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b",  # at 7:30 am / at 7am
        re.I,
    )
    _WEB_RE = re.compile(
        r"https?://|www\.|\b(?:visit|open|fetch|check|read)\s+(?:this\s+)?(?:url|link|site|website|page)\b",
        re.I,
    )

    # Keyword hints: if the query mentions these words, force-include the tools.
    _KEYWORD_HINTS = {
        # NOTE: "tell" was removed from this set. It fired on any "tell me ..."
        # request (e.g. "visit <url> and tell me the title"), force-including the
        # whole email toolset and crowding out the relevant tools — the model then
        # believed it had only email tools and refused web/other tasks (#1707).
        frozenset({"email", "emails", "mail", "mails", "gmail", "googlemail", "message", "messages", "send", "reply", "replies", "inbox", "unread"}):
            {"list_email_accounts", "list_emails", "read_email", "send_email", "reply_to_email", "bulk_email", "delete_email", "archive_email", "mark_email_read", "resolve_contact", "ui_control"},
        frozenset({"calendar", "event", "meeting", "schedule", "appointment"}):
            {"manage_calendar"},
        frozenset({"note", "todo", "reminder", "remind", "checklist", "remember to"}):
            {"manage_notes"},
        frozenset({"todo list", "to-do list", "to do list", "my todos", "todo items",
                   "analyze todos", "list todos", "check todos", "categorize todos",
                   "what's on my todo", "what is on my todo"}):
            {"manage_notes"},
        # Chat/session management. "rename" alone maps to documents below, so a
        # request like "rename the last 12 sessions/chats" needs these session
        # keywords to surface the right tools (NOT app_api — /api/sessions is
        # owner-filtered and returns empty for tool calls).
        frozenset({"sessions", "my chats", "these chats", "those chats",
                   "chat history", "rename chat", "rename session",
                   "rename the chat", "rename my chat", "rename the session",
                   "archive chat", "archive session", "delete chat",
                   "delete session", "fork chat", "fork session",
                   "name the chats", "name my chats", "rename them"}):
            {"list_sessions", "manage_session"},
        frozenset({"recurring", "every day", "every hour", "every morning",
                   "every evening", "every night", "every week", "each morning",
                   "daily task", "background task", "scheduled task", "schedule a",
                   "automatically", "auto-summarize", "auto summarize",
                   "cron", "periodically", "on a schedule", "set up a task",
                   "create a task", "summarize my inbox every", "remind me every"}):
            {"manage_tasks"},
        frozenset({"contact", "address", "phone", "who is"}):
            {"resolve_contact", "manage_contact"},
        frozenset({"save contact", "add contact", "new contact", "update contact",
                   "edit contact", "delete contact", "remove contact",
                   "save this person", "add to contacts", "save to contacts"}):
            {"manage_contact"},
        # "Ask another model" intent → chat_with_model relays to a
        # different model and returns its answer. ask_teacher escalates
        # to the configured teacher. (second_opinion was removed.)
        frozenset({"ask gpt", "ask claude", "ask gemini", "ask deepseek",
                   "ask minimax", "ask qwen", "ask the", "ask another model",
                   "what does", "what would", "second opinion", "other model",
                   "different model", "compare answers", "compare models",
                   "delegate to", "have model"}):
            {"chat_with_model", "ask_teacher", "list_models"},
        # Deep research intent (incl. common typo "reserach")
        frozenset({"research", "reserach", "reasearch", "look into", "investigate",
                   "deep dive", "deep research", "find out about", "study up on",
                   "report on", "do research", "look up everything"}):
            {"trigger_research"},
        # Multi-provider fan-out intent (operator_research).
        frozenset({"search everywhere", "cross-check", "cross check",
                   "all the engines", "every engine", "multiple engines",
                   "broad web sweep", "fan out", "search all providers",
                   "compare sources", "check multiple sources"}):
            {"operator_research"},
        # Screen perception/recall intent (operator tools). Phrases only —
        # a bare "screen" would fire on "screenshot"/"fullscreen" requests.
        frozenset({"my screen", "on screen", "on the screen", "what am i looking",
                   "am i looking at", "screenpipe", "did i see", "when did i see",
                   "saw earlier", "had open", "screen history", "screen recall"}):
            {"screen_look", "screen_recall"},
        # SpecTracer element captures ("the element/button I just grabbed").
        frozenset({"spec trace", "spectracer", "spec tracer", "element i grabbed",
                   "element i just", "i just grabbed", "just captured", "just traced",
                   "i just inspected", "my trace", "the trace i"}):
            {"spec_trace"},
        # Desktop control intent (operator desktop_act via Clicky).
        frozenset({"click the", "click on", "double click", "double-click",
                   "move the mouse", "move my mouse", "drag the", "click that",
                   "press the button on", "control my desktop", "control the mouse"}):
            {"desktop_act", "screen_look"},
        # Browser control intent (operator browser_act via CDP).
        frozenset({"my browser", "in chrome", "open tabs", "my tabs",
                   "in my browser", "on the page", "on this page", "browser tab",
                   "navigate to", "fill in the form", "fill the form",
                   "the login button", "in the browser"}):
            {"browser_act"},
        # Settings-change intent — "change my…/set my…/use X for…/turn on…".
        frozenset({"change my", "set my", "use the voice", "change the voice",
                   "my voice", "tts voice", "search engine", "default model",
                   "teacher model", "task model", "background model", "image quality",
                   "reminder channel", "send reminders to", "remind me by",
                   "speak faster", "speak slower", "agent timeout", "token budget",
                   "max tool calls", "use this model for", "use that model for",
                   "my settings", "change setting", "change a setting", "set setting",
                   "preference", "preferences", "configure"}):
            {"manage_settings", "ui_control"},
        # Managing EXISTING research in the Library — open/read/find/delete.
        frozenset({"my research", "the research", "research on", "open research",
                   "read research", "find research", "delete research",
                   "remove research", "list research", "my reports", "the report",
                   "saved research", "research library", "past research",
                   "research i did", "research about"}):
            {"manage_research", "trigger_research"},
        # Document edit/update intent
        frozenset({"edit", "change", "fix", "rewrite", "update",
                   "replace", "add a", "tweak", "modify", "rename", "paragraph",
                   "section", "line", "the doc", "the docs", "the document", "the documents", "in the doc", "in the docs", "in document"}):
            {"edit_document", "update_document", "create_document", "suggest_document"},
        # Document deletion / management — include generic open/find/read/show
        # verbs + file/doc synonyms so "open my <X>", "find the <X>", "delete
        # <X>" reach manage_documents even without the literal word "document".
        frozenset({"delete this doc", "delete the doc", "delete document",
                   "remove document", "remove the doc", "trash", "list document", "list documents",
                   "list doc", "list docs", "all my docs", "my document", "my documents", "my doc", "my docs", "my files",
                   "open the", "open my", "open document", "open doc", "find the",
                   "find my", "find document", "read the", "read my", "show me the",
                   "show my", "the file", "my file", "the report", "the write-up",
                   "the writeup", "saved document", "in my library", "in the library"}):
            {"manage_documents", "edit_document"},
        # Theme / UI control intent
        frozenset({"theme", "color scheme", "colors of the ui", "make it dark",
                   "make it light", "make the ui", "switch theme", "change theme",
                   "dark mode", "light mode", "toggle"}):
            {"ui_control"},
        # Cookbook / model serving intent — user says "kill cookbook",
        # "stop the model", "what's running", etc.
        frozenset({"cookbook", "kill cookbook", "stop cookbook",
                   "stop the model", "kill the model", "kill my model",
                   "what's running", "what is running", "whats running",
                   "running models", "running model", "running server",
                   "shut down vllm", "shutdown vllm", "stop vllm",
                   "stop serving", "kill serve", "cancel serve"}):
            {"list_served_models", "stop_served_model"},
        # Cookbook serve / launch / preset / server selection
        frozenset({"serve", "launch", "spin up", "start the model", "run the model",
                   "preset", "presets", "which server", "what servers",
                   "gpu box", "cookbook server", "vllm", "on the server", "on the gpu"}):
            {"serve_preset", "serve_model", "list_serve_presets",
             "list_cookbook_servers", "list_cached_models"},
        # Cookbook downloads
        frozenset({"download", "downloading", "downloads",
                   "cancel download", "stop download", "kill download",
                   "what's downloading", "download progress", "pull model", "grab model"}):
            {"list_downloads", "cancel_download", "download_model",
             "list_cookbook_servers"},
        # HuggingFace search + cached model browse
        frozenset({"huggingface", "hugging face", "hf search",
                   "find a model", "search models", "search for a model",
                   "models for", "best model for"}):
            {"search_hf_models", "list_cached_models"},
        frozenset({"cached models", "list models", "my models",
                   "what models do i have", "is it downloaded",
                   "do i have", "already downloaded", "on disk"}):
            {"list_cached_models", "search_hf_models"},
        # Tool on/off / panel open intent — user says "turn off shell",
        # "disable search", "open library", "show gallery", etc.
        frozenset({"turn off", "turn on", "disable", "enable",
                   "shell off", "shell on", "search off", "search on",
                   "research off", "research on", "incognito",
                   "switch model", "change model", "set mode", "agent mode", "chat mode",
                   "open library", "open documents", "open gallery", "open email",
                   "open inbox", "open settings", "open memories", "open memory",
                   "open skills", "open notes", "open chats", "open sessions",
                   "show library", "show gallery", "show inbox", "show settings",
                   "show memory", "show memories", "show skills", "show notes",
                   "show chats", "show sessions", "show documents"}):
            {"ui_control"},
        # Document creation intent
        frozenset({"write a", "create a doc", "draft", "compose", "poem", "story",
                   "essay", "outline", "letter"}):
            {"create_document", "edit_document", "update_document"},
        # Video transcription / video-brief intent
        frozenset({"transcribe", "transcript", "transcription",
                   "youtube video", "this video", "the video", "youtube link",
                   "brief this video", "summarize this video", "video brief"}):
            {"transcribe_video"},
    }

    def get_tools_for_query(
        self, query: str, k: int = 8, always_include: Optional[Set[str]] = None
    ) -> Set[str]:
        """Get the set of tool names to include for a given user query."""
        base = set(always_include or ALWAYS_AVAILABLE)
        retrieved = self.retrieve(query, k=k)
        base.update(retrieved)
        # Keyword-based force-include for common intents. Match on word
        # boundaries, not raw substrings, so short hints like "fix", "line",
        # "serve", "reply" or "unread" don't fire inside unrelated words
        # ("prefix", "deadline"/"online", "observe"/"reserve", "replying",
        # "unreadable"). Same word-boundary matching used in topic_analyzer.
        ql = query.lower()
        for keywords, tools in self._KEYWORD_HINTS.items():
            if any(re.search(rf"\b{re.escape(kw)}\b", ql) for kw in keywords):
                base.update(tools)
        # Structural scheduling-intent detection — typo-resilient (the literal
        # keyword "every day" misses "every dya"). Catches "every <word>",
        # daily/nightly/etc., or a clock time like "at 7:30 am" / "7am", which
        # all signal a recurring/scheduled task. Force-include manage_tasks so
        # the agent can actually create the cron job instead of fumbling.
        if self._SCHEDULE_RE.search(ql):
            base.add("manage_tasks")
        # URL/site requests need web tools even when embedding retrieval is
        # stubbed/unavailable. Keep this structural, not always-on, so trivial
        # prompts do not drag web schemas into the agent context.
        if self._WEB_RE.search(query):
            base.update({"web_search", "web_fetch"})
        return base


# ── Singleton ──

_tool_index: Optional[ToolIndex] = None
_last_attempt = 0.0
_RETRY_INTERVAL = 30.0
_init_lock = threading.Lock()


def peek_tool_index() -> Optional[ToolIndex]:
    """Return the warm singleton without loading MiniLM or indexing."""
    if _tool_index is not None and _tool_index.healthy:
        return _tool_index
    return None


def _on_asyncio_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def get_tool_index() -> Optional[ToolIndex]:
    """Get or create the singleton ToolIndex. Returns None if unavailable.

    MiniLM/ONNX load must not run on the uvicorn event loop. Callers already
    on the loop get the warm singleton or None — use asyncio.to_thread to init.
    """
    global _tool_index, _last_attempt

    existing = peek_tool_index()
    if existing is not None:
        return existing

    if _on_asyncio_loop():
        logger.debug("ToolIndex not ready; refusing MiniLM load on the event loop")
        return None

    with _init_lock:
        existing = peek_tool_index()
        if existing is not None:
            return existing

        now = time.monotonic()
        if now - _last_attempt < _RETRY_INTERVAL:
            return None
        _last_attempt = now
        try:
            _tool_index = ToolIndex()
            _tool_index.index_builtin_tools()
            return _tool_index
        except Exception as e:
            logger.warning(f"ToolIndex init failed (will retry in {_RETRY_INTERVAL}s): {e}")
            _tool_index = None
            return None


def reset_tool_index() -> None:
    """Clear the singleton so embedding endpoint changes rebuild tool lanes."""
    global _tool_index, _last_attempt
    with _init_lock:
        _tool_index = None
        _last_attempt = 0.0
