"""Build cross-agent handoff markdown packets (mirrors static/js/handoff.js)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

HANDOFF_TITLE_PREFIX = "handoff → "
VALID_TARGETS = frozenset({"cursor", "claude", "odysseus", "hermes"})
TARGET_ALIASES = {
    "claude-code": "claude",
    "claude_code": "claude",
    "cc": "claude",
    "cursor-ide": "cursor",
    "cursor_ide": "cursor",
    "ody": "odysseus",
    "odysseus-ui": "odysseus",
    "brudda": "hermes",
}


def normalize_target(name: str) -> str:
    key = (name or "").strip().lower()
    return TARGET_ALIASES.get(key, key)


def handoff_doc_title(target: str, title: str) -> str:
    return f"{HANDOFF_TITLE_PREFIX}{target}: {(title or '').strip()}"


def parse_handoff_target_from_title(title: str) -> str:
    """Extract relay target from a handoff document title."""
    text = (title or "").strip()
    if not text.startswith(HANDOFF_TITLE_PREFIX):
        return ""
    rest = text[len(HANDOFF_TITLE_PREFIX) :]
    if ":" not in rest:
        return ""
    return normalize_target(rest.split(":", 1)[0].strip())


def handoff_subject_from_doc_title(title: str) -> str:
    """Subject line after ``handoff → {target}:``."""
    text = (title or "").strip()
    if not text.startswith(HANDOFF_TITLE_PREFIX):
        return text
    rest = text[len(HANDOFF_TITLE_PREFIX) :]
    if ":" in rest:
        return rest.split(":", 1)[1].strip()
    return rest.strip()


def pickup_hint(target: str, doc_id: str) -> str:
    doc_id = str(doc_id or "")
    if target in ("cursor", "claude", "hermes"):
        return f"Pick up handoff {doc_id}"
    return f"Pick up handoff {doc_id}"


def _bootstrap_block(target: str, project: str) -> str:
    lines = ["## Agent bootstrap", ""]
    project_path = (project or "").strip()
    if project_path:
        if "\\" in project_path or project_path[1:3] == ":\\":
            lines.extend(["```powershell", f'cd "{project_path}"', "```", ""])
        else:
            lines.extend(["```bash", f"cd {project_path!r}", "```", ""])
    if target == "cursor":
        lines.append("In Cursor, run the bootstrap block above, then execute **Next steps**.")
    elif target == "claude":
        lines.append("In Claude Code, run the bootstrap block above, then execute **Next steps**.")
    elif target == "hermes":
        lines.append(
            "In Hermes, run `handoff_api.py list --pending` or say **Pick up handoff**, "
            "then execute **Next steps**."
        )
    else:
        lines.append("In Odysseus, read **Goal** and **Next steps** — continue in chat or link the session.")
    lines.append("")
    return "\n".join(lines)


def build_handoff_content(
    *,
    source: str,
    target: str,
    project: str = "",
    goal: str = "",
    context: list[str] | None = None,
    done: list[str] | None = None,
    next_steps: list[str] | None = None,
    note_body: str = "",
    session_id: str = "",
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    frontmatter = [
        "---",
        "handoff_version: 1",
        f"source: {source}",
        f"target: {target}",
        "status: pending",
        f"project: {project or ''}",
        f"created_at: {now}",
    ]
    if session_id:
        frontmatter.append(f"session_id: {session_id}")
    frontmatter.extend(["---", ""])

    parts = ["\n".join(frontmatter)]
    if goal:
        parts.append(f"## Goal\n\n{goal.strip()}\n")
    if context:
        parts.append("## Context\n")
        parts.extend(f"- {item}" for item in context)
        parts.append("")
    if note_body:
        parts.append(f"## Notes\n\n{note_body.strip()}\n")
    if done:
        parts.append("## Done so far\n")
        parts.extend(f"- {item}" for item in done)
        parts.append("")
    if next_steps:
        parts.append("## Next steps\n")
        parts.extend(f"- {item}" for item in next_steps)
        parts.append("")
    parts.append(_bootstrap_block(target, project))
    return "\n".join(parts)


def build_note_handoff_fields(note: dict[str, Any]) -> dict[str, Any]:
    """Derive handoff sections from a note dict (API shape)."""
    title = (note.get("title") or "").strip()
    content = (note.get("content") or "").strip()
    label = (note.get("label") or "").strip()
    note_type = note.get("note_type") or "note"
    items = note.get("items") if isinstance(note.get("items"), list) else []

    goal = title
    if not goal and content:
        goal = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
    if not goal and items:
        for it in items:
            if isinstance(it, dict) and (it.get("text") or "").strip():
                goal = it["text"].strip()
                break
    if not goal:
        goal = f"Note handoff ({datetime.now().strftime('%Y-%m-%d %H:%M')})"

    context = [f"Odysseus note type: {note_type}"]
    if note.get("id"):
        context.append(f"Note ID: {note['id']}")
    if label:
        context.append(f"Tags: {label}")
    if note.get("due_date"):
        context.append(f"Reminder: {note['due_date']}")

    done: list[str] = []
    pending: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = (it.get("text") or "").strip()
        if not text:
            continue
        if it.get("done") or it.get("checked"):
            done.append(text)
        else:
            pending.append(text)

    body_parts: list[str] = []
    if title:
        body_parts.append(f"# {title}")
    if content:
        body_parts.append(content)
    if pending:
        body_parts.append("")
        body_parts.append("Open items:")
        body_parts.extend(f"- [ ] {t}" for t in pending)
    if done:
        body_parts.append("")
        body_parts.append("Completed items:")
        body_parts.extend(f"- [x] {t}" for t in done)

    next_steps = [
        "Decompose the goal into smaller jobs and a concrete plan.",
        "Execute the plan in order — ship working changes, not just suggestions.",
        "Report what was done and what remains.",
    ]
    if pending:
        next_steps.insert(
            0,
            f"Tackle the {len(pending)} open checklist item{'s' if len(pending) != 1 else ''} first.",
        )

    return {
        "title": goal[:120],
        "goal": goal,
        "context": context,
        "done": done,
        "next_steps": next_steps,
        "note_body": "\n".join(body_parts).strip(),
        "session_id": note.get("agent_session_id") or note.get("session_id") or "",
    }
