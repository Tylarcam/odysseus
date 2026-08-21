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
import re
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

# Human-gate confirms: tick checklist / mark draft sent. Never SMTP, never Upwork/CIHR submit.
CONFIRM_SEND_ACTIONS: Tuple[str, ...] = (
    "confirm_pack_sent",
    "confirm_proposal_sent",
    "confirm_npr_sent",
    "confirm_grant_packet_sent",
)
SEND_PACK_CHECKLIST_PREFIX = "f1cf1f16"
GRANT_PACKET_CHECKLIST_PREFIX = "08e7c105"

# CMD Center actions safe to trigger from voice (UI navigation / soft acts).
CMD_NAVIGATE_ACTIONS: Tuple[str, ...] = (
    "agent_bin",
    "jobs",
    "notes",
    "open_note",
    "open_doc",
    "email",
    "research",
    "calendar",
    "library",
    "tasks",
    "plan_today",
    "refresh",
) + CONFIRM_SEND_ACTIONS

# Realtime context is small — clamp tool output so one big result can't
# blow the session (the model summarizes it into speech anyway).
_MAX_OUTPUT_CHARS = 6000
_TOOL_TIMEOUT_SECONDS = 90

_CMD_NAVIGATE_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "name": "cmd_navigate",
    "description": (
        "Navigate Odysseus CMD Center / vault UI. Use for spoken shortcuts like "
        "'open agent bin', 'open jobs', 'open the send pack', 'open that document', "
        "'plan today', 'open email', 'open research'. action=open_doc opens a Library "
        "document (pass id); action=open_note opens a MEM note. "
        "After the human actually sent: confirm_pack_sent ('I sent the pack' / "
        "'mark the send pack done' / 'check off the send pack') ticks checklist "
        "f1cf1f16; confirm_proposal_sent ('I sent proposal 1') ticks the first "
        "unchecked pack item; confirm_npr_sent ('I sent the NPR thank-you') marks "
        "draft 4be22ee3 then the next unsent NPR thank-you; confirm_grant_packet_sent "
        "('I submitted the nomination' / 'I submitted Impact+') ticks checklist "
        "08e7c105. Confirms only — never submit to Upwork, never submit to CIHR, "
        "never send SMTP."
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
_MEMORY_ACTIONS = frozenset({"list", "add", "edit", "delete", "search", "pin", "unpin"})
_CUSTOM_SCHEMAS = frozenset({"cmd_navigate", "manage_research", "list_handoffs", "manage_memory"})

_MANAGE_MEMORY_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "name": "manage_memory",
    "description": (
        "Manage persistent memories (facts, identity, money facts). "
        "Actions: list, add, edit, delete, search, pin, unpin. "
        "Spoken pin: 'pin that money fact', 'keep this in memory', "
        "'pin that', 'unpin that fact'. pin/unpin need memory_id from list "
        "or search. Pin does not delete — it flags the fact for always-on "
        "Jarvis context (same as POST /api/memory/{id}/pin)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "edit", "delete", "search", "pin", "unpin"],
                "description": "The action. pin/unpin toggle always-on voice context.",
            },
            "text": {
                "type": "string",
                "description": "Memory text (for add/edit) or search query (for search)",
            },
            "memory_id": {
                "type": "string",
                "description": "Memory ID (for edit/delete/pin/unpin)",
            },
            "category": {
                "type": "string",
                "enum": ["fact", "event", "contact", "preference"],
                "description": "Memory category (for add/list filter)",
            },
            "pinned": {
                "type": "boolean",
                "description": "For action=pin: true pins, false unpins (default true).",
            },
        },
        "required": ["action"],
    },
}


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
    if "manage_memory" in VOICE_TOOL_NAMES and "manage_memory" not in seen:
        schemas.append(dict(_MANAGE_MEMORY_SCHEMA))
        seen.add("manage_memory")
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


_SENT_TITLE_MARK = re.compile(
    r"\((sent|cleared|done)\)|marked sent|already sent",
    re.IGNORECASE,
)


def _parse_note_items(note: Any) -> List[Dict[str, Any]]:
    raw = getattr(note, "items", None)
    if isinstance(raw, list):
        return [it for it in raw if isinstance(it, dict)]
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [it for it in data if isinstance(it, dict)]


def _dump_note_items(items: List[Dict[str, Any]]) -> str:
    return json.dumps(items)


def _mark_title_sent(title: str) -> str:
    t = (title or "").strip()
    if _SENT_TITLE_MARK.search(t):
        return t
    return f"{t} (sent)" if t else "(sent)"


def _item_open(it: Dict[str, Any]) -> bool:
    return not it.get("done") and not it.get("checked")


def _is_sent_note(note: Any) -> bool:
    if getattr(note, "archived", False):
        return True
    if _SENT_TITLE_MARK.search(str(getattr(note, "title", "") or "")):
        return True
    items = _parse_note_items(note)
    if items:
        return all(not _item_open(it) for it in items)
    return False


def _npr_id_match(rec_id: str, prefix: str) -> bool:
    nid = str(rec_id or "").strip()
    if not nid or not prefix:
        return False
    return nid == prefix or nid.startswith(prefix) or prefix.startswith(nid[:8])


def _notes_matching_prefix(db: Any, prefix: str, owner: Optional[str]) -> List[Any]:
    from core.database import Note
    from src.auth_helpers import owner_filter

    q = db.query(Note)
    if owner and owner != "anonymous":
        q = owner_filter(q, Note, owner)
    try:
        q = q.filter(Note.id.like(f"{prefix}%"))
    except Exception:
        pass
    try:
        rows = q.all()
    except Exception:
        row = q.first() if hasattr(q, "first") else None
        rows = [row] if row is not None else []
    return [row for row in rows if _npr_id_match(getattr(row, "id", ""), prefix)]


def confirm_human_send(
    action: str,
    owner: Optional[str] = None,
    *,
    db: Any = None,
) -> Dict[str, Any]:
    """Record that the operator already sent. Never SMTP, never Upwork/CIHR submit.

    confirm_pack_sent: mark checklist f1cf1f16 items done + title (sent).
    confirm_proposal_sent: tick the first unchecked item on that checklist.
    confirm_npr_sent: mark the first unsent NPR thank-you (4be22ee3 then next).
    confirm_grant_packet_sent: mark checklist 08e7c105 items done + title (sent).
    """
    from core.database import SessionLocal
    from services.home.mycelia_feed import NPR_PANEL2_DRAFT_IDS

    act = (action or "").strip()
    if act not in CONFIRM_SEND_ACTIONS:
        return {"ok": False, "error": f"Not a confirm-send action: {act}", "submit": False}

    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        if act in ("confirm_pack_sent", "confirm_proposal_sent"):
            notes = _notes_matching_prefix(db, SEND_PACK_CHECKLIST_PREFIX, owner)
            if not notes:
                return {
                    "ok": False,
                    "submit": False,
                    "action": act,
                    "error": f"Send pack checklist {SEND_PACK_CHECKLIST_PREFIX} not found.",
                }
            note = notes[0]
            items = _parse_note_items(note)
            if act == "confirm_proposal_sent":
                ticked = 0
                for it in items:
                    if _item_open(it):
                        it["done"] = True
                        ticked = 1
                        break
                if not ticked:
                    return {
                        "ok": True,
                        "already": True,
                        "submit": False,
                        "action": act,
                        "id": str(getattr(note, "id", "") or ""),
                        "speech": "All pack proposals are already checked off.",
                    }
                note.items = _dump_note_items(items)
                if items and all(not _item_open(it) for it in items):
                    note.title = _mark_title_sent(str(note.title or ""))
                db.commit()
                open_left = sum(1 for it in items if _item_open(it))
                speech = (
                    "Logged one pack proposal as sent. Not submitting to Upwork."
                    if open_left
                    else "Logged the last pack proposal as sent. Not submitting to Upwork. Fruit will land on the next brief."
                )
                return {
                    "ok": True,
                    "submit": False,
                    "action": act,
                    "id": str(getattr(note, "id", "") or ""),
                    "marked": ticked,
                    "open_left": open_left,
                    "speech": speech,
                }

            if items and all(not _item_open(it) for it in items) and _is_sent_note(note):
                return {
                    "ok": True,
                    "already": True,
                    "submit": False,
                    "action": act,
                    "id": str(getattr(note, "id", "") or ""),
                    "speech": "Send pack is already marked sent.",
                }
            marked = 0
            for it in items:
                if _item_open(it):
                    marked += 1
                it["done"] = True
            if items:
                note.items = _dump_note_items(items)
            note.title = _mark_title_sent(str(note.title or ""))
            db.commit()
            n = marked or len(items) or 5
            return {
                "ok": True,
                "submit": False,
                "action": act,
                "id": str(getattr(note, "id", "") or ""),
                "marked": n,
                "speech": (
                    f"Logged the send pack as sent ({n} proposals). "
                    "Not submitting to Upwork. Fruit will land on the next brief."
                ),
            }

        if act == "confirm_grant_packet_sent":
            notes = _notes_matching_prefix(db, GRANT_PACKET_CHECKLIST_PREFIX, owner)
            if not notes:
                return {
                    "ok": False,
                    "submit": False,
                    "action": act,
                    "error": (
                        f"Impact+ packet checklist {GRANT_PACKET_CHECKLIST_PREFIX} not found."
                    ),
                }
            note = notes[0]
            items = _parse_note_items(note)
            if items and all(not _item_open(it) for it in items) and _is_sent_note(note):
                return {
                    "ok": True,
                    "already": True,
                    "submit": False,
                    "action": act,
                    "id": str(getattr(note, "id", "") or ""),
                    "speech": "Impact+ nomination is already marked submitted.",
                }
            marked = 0
            for it in items:
                if _item_open(it):
                    marked += 1
                it["done"] = True
            if items:
                note.items = _dump_note_items(items)
            note.title = _mark_title_sent(str(note.title or ""))
            db.commit()
            n = marked or len(items) or 1
            return {
                "ok": True,
                "submit": False,
                "action": act,
                "id": str(getattr(note, "id", "") or ""),
                "marked": n,
                "speech": (
                    f"Logged the Impact+ nomination as submitted ({n} checklist items). "
                    "Not submitting to CIHR. Fruit will land on the next brief."
                ),
            }

        # NPR thank-you: 4be22ee3, then 8504c427, then 80aa4a73.
        for prefix in NPR_PANEL2_DRAFT_IDS:
            notes = _notes_matching_prefix(db, prefix, owner)
            if not notes:
                continue
            note = notes[0]
            if _is_sent_note(note):
                continue
            note.title = _mark_title_sent(str(note.title or ""))
            items = _parse_note_items(note)
            if items:
                for it in items:
                    it["done"] = True
                note.items = _dump_note_items(items)
            db.commit()
            nid = str(getattr(note, "id", "") or "")[:8] or prefix
            return {
                "ok": True,
                "submit": False,
                "action": act,
                "id": str(getattr(note, "id", "") or ""),
                "speech": (
                    f"Logged NPR thank-you {nid} as sent. Not sending SMTP. "
                    "Fruit will land on the next brief."
                ),
            }
        return {
            "ok": True,
            "already": True,
            "submit": False,
            "action": act,
            "speech": "NPR thank-you drafts are already marked sent.",
        }
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error("confirm_human_send failed: %s", e, exc_info=True)
        return {"ok": False, "submit": False, "action": act, "error": str(e)}
    finally:
        if close:
            try:
                db.close()
            except Exception:
                pass


def _coerce_pinned_flag(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("0", "false", "no", "off", "unpin", "unpinned"):
        return False
    if text in ("1", "true", "yes", "on", "pin", "pinned"):
        return True
    return default


def pin_memory_for_voice(
    memory_id: str,
    pinned: bool = True,
    owner: Optional[str] = None,
) -> Dict[str, Any]:
    """Voice entry point for POST /api/memory/{id}/pin (same service)."""
    from src.ai_interaction import _memory_manager
    from src.memory import pin_memory_item

    if not _memory_manager:
        return {"ok": False, "error": "Memory manager not available"}
    return pin_memory_item(_memory_manager, memory_id, pinned=pinned, owner=owner)


def _execute_memory_pin(
    action: str,
    args: Dict[str, Any],
    owner: Optional[str] = None,
) -> str:
    memory_id = str(args.get("memory_id") or args.get("id") or "").strip()
    if not memory_id:
        return "Error: pin/unpin needs memory_id. Call action=list or search first."
    want_pin = True if action == "pin" else False
    if action == "pin":
        want_pin = _coerce_pinned_flag(args.get("pinned"), default=True)
    result = pin_memory_for_voice(memory_id, pinned=want_pin, owner=owner)
    if not result.get("ok"):
        return f"Error: {result.get('error') or 'could not pin memory'}"
    state = "pinned" if result.get("pinned") else "unpinned"
    mid = result.get("memory_id") or memory_id
    return f"Memory {mid} is now {state}."


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
        if resolved["action"] in CONFIRM_SEND_ACTIONS:
            result = confirm_human_send(resolved["action"], owner=owner)
            if not result.get("ok"):
                return f"Error: {result.get('error') or 'could not log send'}"
            return str(result.get("speech") or "Logged as sent. Not submitting.")
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

    if name == "manage_memory":
        action = (args.get("action") or "list").strip().lower()
        if action not in _MEMORY_ACTIONS:
            return (
                f"Error: unknown memory action '{action}'. "
                f"Use: {', '.join(sorted(_MEMORY_ACTIONS))}."
            )
        if action in ("pin", "unpin"):
            return _execute_memory_pin(action, args, owner=owner)

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
