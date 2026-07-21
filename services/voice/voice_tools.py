# services/voice/voice_tools.py
"""Curated tool set for realtime voice sessions.

Realtime voice can't run the full agent loop, but it can call a small,
voice-safe subset of Odysseus tools via OpenAI Realtime function calling.
The browser receives the function_call event on the data channel, POSTs it
to /api/voice/tool-call, and returns the output to the realtime session.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Voice-safe tools: read/lookup heavy, no shell/code execution, no
# destructive bulk operations. Names match FUNCTION_TOOL_SCHEMAS except
# cmd_navigate (custom schema below).
VOICE_TOOL_NAMES: Tuple[str, ...] = (
    "web_search",
    "web_fetch",
    "manage_notes",
    "manage_calendar",
    "manage_memory",
    "list_emails",
    "read_email",
    "manage_research",
    "list_handoffs",
    "process_job_application",
    "cmd_navigate",
)

# CMD Center actions safe to trigger from voice (UI navigation / soft acts).
CMD_NAVIGATE_ACTIONS: Tuple[str, ...] = (
    "agent_bin",
    "jobs",
    "notes",
    "open_note",
    "email",
    "research",
    "calendar",
    "library",
    "tasks",
    "plan_today",
    "refresh",
)

# Realtime context is small — clamp tool output so one big result can't
# blow the session (the model summarizes it into speech anyway).
_MAX_OUTPUT_CHARS = 6000
_TOOL_TIMEOUT_SECONDS = 90

_CMD_NAVIGATE_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "name": "cmd_navigate",
    "description": (
        "Navigate Odysseus CMD Center / vault UI. Use for spoken shortcuts like "
        "'open agent bin', 'open jobs', 'plan today', 'open email', 'open research'. "
        "Does not send email or run shell."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(CMD_NAVIGATE_ACTIONS),
                "description": "CMD Center action id",
            },
            "id": {
                "type": "string",
                "description": "Optional note/task/session id when opening a specific item",
            },
        },
        "required": ["action"],
    },
}

# manage_research is a first-class agent tool but may not be in FUNCTION_TOOL_SCHEMAS.
_MANAGE_RESEARCH_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "name": "manage_research",
    "description": (
        "List or read saved deep-research reports from the Library. "
        "action=list returns recent reports; action=read needs id. "
        "Voice mode does not delete or start new research."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "read"],
                "description": "list or read",
            },
            "id": {"type": "string", "description": "Research session id (for read)"},
            "search": {"type": "string", "description": "Optional list filter"},
        },
        "required": ["action"],
    },
}

_LIST_HANDOFFS_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "name": "list_handoffs",
    "description": (
        "List Agent Bin handoffs waiting for pickup (needs_attention / in_progress). "
        "Use for 'what's waiting in the agent bin', 'top handoff', or Relay status. "
        "Read-only — does not claim or complete handoffs. Pair with cmd_navigate "
        "action=agent_bin to open the UI."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "bucket": {
                "type": "string",
                "enum": ["needs_attention", "in_progress", "all"],
                "description": "Which bucket to summarize (default needs_attention)",
            },
            "limit": {
                "type": "integer",
                "description": "Max handoffs to return (default 5, max 12)",
            },
        },
        "required": [],
    },
}

# Read-only / voice-safe action filters for tools that also support writes.
_JOB_SAFE_ACTIONS = frozenset({"list", "status", "get", "ready_to_apply"})
_RESEARCH_SAFE_ACTIONS = frozenset({"list", "read", "open", "view", "get"})
_CUSTOM_SCHEMAS = frozenset({"cmd_navigate", "manage_research", "list_handoffs"})


def get_voice_tool_schemas() -> List[Dict[str, Any]]:
    """Voice tool schemas in Realtime session format (flattened, not nested)."""
    import src.agent_tools  # noqa: F401 — must load before tool_schemas (circular import)
    from src.tool_schemas import FUNCTION_TOOL_SCHEMAS

    schemas = []
    seen = set()
    for entry in FUNCTION_TOOL_SCHEMAS:
        fn = entry.get("function") or {}
        name = fn.get("name")
        if name not in VOICE_TOOL_NAMES or name in _CUSTOM_SCHEMAS:
            continue
        schemas.append({
            "type": "function",
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
        })
        seen.add(name)
    if "manage_research" in VOICE_TOOL_NAMES and "manage_research" not in seen:
        schemas.append(dict(_MANAGE_RESEARCH_SCHEMA))
        seen.add("manage_research")
    if "list_handoffs" in VOICE_TOOL_NAMES and "list_handoffs" not in seen:
        schemas.append(dict(_LIST_HANDOFFS_SCHEMA))
        seen.add("list_handoffs")
    if "cmd_navigate" in VOICE_TOOL_NAMES:
        schemas.append(dict(_CMD_NAVIGATE_SCHEMA))
        seen.add("cmd_navigate")
    return schemas


def _format_handoff_line(note: Dict[str, Any]) -> str:
    title = (note.get("title") or "Untitled handoff").strip()
    target = (note.get("handoff_target") or "?").strip()
    status = (note.get("handoff_relay_status") or "waiting").strip() or "waiting"
    hid = (note.get("id") or "")[:8]
    return f"- {title} → {target} [{status}] id={hid}"


def list_handoffs_for_voice(
    owner: Optional[str] = None,
    bucket: str = "needs_attention",
    limit: int = 5,
) -> str:
    """Summarize Agent Bin handoffs for speech."""
    from core.database import Note, SessionLocal
    from routes.home_routes import _note_row_to_cmd
    from src.auth_helpers import owner_filter
    from src.handoff_bin import bucket_handoff_notes

    lim = max(1, min(int(limit or 5), 12))
    buck = (bucket or "needs_attention").strip().lower()
    if buck not in ("needs_attention", "in_progress", "all"):
        buck = "needs_attention"

    db = SessionLocal()
    try:
        q = db.query(Note).filter(Note.handoff_doc_id.isnot(None))
        if owner and owner != "anonymous":
            q = owner_filter(q, Note, owner)
        rows = [_note_row_to_cmd(n) for n in q.order_by(Note.updated_at.desc()).limit(40).all()]
    finally:
        db.close()

    buckets = bucket_handoff_notes(rows)
    counts = buckets.get("counts") or {}
    header = (
        f"Handoffs: {counts.get('needs_attention', 0)} waiting · "
        f"{counts.get('in_progress', 0)} in progress · "
        f"{counts.get('done', 0)} done"
    )
    if buck == "all":
        items = (buckets.get("needs_attention") or []) + (buckets.get("in_progress") or [])
    else:
        items = buckets.get(buck) or []

    if not items:
        return header + f"\nNo handoffs in '{buck}'."

    lines = [header, f"Top {min(lim, len(items))} ({buck}):"]
    for note in items[:lim]:
        lines.append(_format_handoff_line(note))
    return "\n".join(lines)


def _flatten_result(result: Any) -> str:
    """Collapse a tool result dict into plain text for the realtime model."""
    if result is None:
        return ""
    if isinstance(result, str):
        text = result
    elif isinstance(result, dict):
        for key in ("output", "results", "response", "stdout", "content"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                text = val
                break
        else:
            if result.get("error"):
                text = f"Error: {result['error']}"
            else:
                try:
                    text = json.dumps(result, ensure_ascii=False, default=str)
                except (TypeError, ValueError):
                    text = str(result)
    else:
        text = str(result)

    text = text.strip()
    if len(text) > _MAX_OUTPUT_CHARS:
        text = text[:_MAX_OUTPUT_CHARS] + "\n[output truncated]"
    return text


def resolve_cmd_action(action: str, target_id: Optional[str] = None) -> Dict[str, Any]:
    """Validate a CMD navigate action (server-side whitelist)."""
    act = (action or "").strip()
    if act not in CMD_NAVIGATE_ACTIONS:
        return {
            "ok": False,
            "error": f"Action '{act}' is not allowed from voice. "
            f"Allowed: {', '.join(CMD_NAVIGATE_ACTIONS)}",
        }
    return {"ok": True, "action": act, "id": (target_id or "").strip()}


async def execute_voice_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    owner: Optional[str] = None,
) -> str:
    """Execute one whitelisted tool and return its output as plain text.

    Raises ValueError for unknown/disallowed tools; other failures come
    back as an "Error: ..." string so the voice model can relay them.
    """
    if name not in VOICE_TOOL_NAMES:
        raise ValueError(f"Tool '{name}' is not available in voice mode")

    args = dict(arguments or {})

    if name == "cmd_navigate":
        resolved = resolve_cmd_action(args.get("action") or "", args.get("id"))
        if not resolved.get("ok"):
            return f"Error: {resolved.get('error')}"
        # UI navigation is applied client-side via odysseus:cmd-action.
        return (
            f"CMD action queued: {resolved['action']}"
            + (f" (id={resolved['id']})" if resolved.get("id") else "")
            + ". The vault UI should open that surface now."
        )

    if name == "list_handoffs":
        try:
            return list_handoffs_for_voice(
                owner=owner,
                bucket=str(args.get("bucket") or "needs_attention"),
                limit=int(args.get("limit") or 5),
            )
        except Exception as e:
            logger.error("list_handoffs failed: %s", e, exc_info=True)
            return f"Error: could not list handoffs ({e})"

    if name == "process_job_application":
        action = (args.get("action") or "list").strip().lower()
        if action not in _JOB_SAFE_ACTIONS:
            return (
                "Error: voice mode only allows job pipeline list/status/get/"
                "ready_to_apply. Use agent mode for tailor/apply/mark_applied."
            )
        args["action"] = action

    if name == "manage_research":
        action = (args.get("action") or "list").strip().lower()
        if action not in _RESEARCH_SAFE_ACTIONS:
            return (
                "Error: voice mode only allows research list/read. "
                "Use agent mode to delete or start new deep research."
            )
        if action in ("open", "view", "get"):
            args["action"] = "read"

    import src.agent_tools  # noqa: F401 — must load before tool_schemas (circular import)
    from src.tool_execution import execute_tool_block
    from src.tool_schemas import function_call_to_tool_block

    args_json = json.dumps(args)
    block = function_call_to_tool_block(name, args_json)
    if block is None:
        raise ValueError(f"Could not build a tool call for '{name}'")

    try:
        _desc, result = await asyncio.wait_for(
            execute_tool_block(block, owner=owner),
            timeout=_TOOL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("voice tool '%s' timed out after %ss", name, _TOOL_TIMEOUT_SECONDS)
        return f"Error: the {name} tool timed out. Tell the user it took too long."
    except Exception as e:
        logger.error("voice tool '%s' failed: %s", name, e, exc_info=True)
        return f"Error: {e}"

    return _flatten_result(result)
