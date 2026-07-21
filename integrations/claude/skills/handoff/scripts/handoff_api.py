#!/usr/bin/env python3
"""Odysseus handoff packet helper — create, list, and pick up cross-agent handoffs."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

HANDOFF_TITLE_PREFIX = "handoff → "
VALID_TARGETS = {"cursor", "claude", "odysseus", "hermes"}
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


def _usage() -> int:
    print(
        "usage:\n"
        "  handoff_api.py create TARGET --from SOURCE --title TITLE [options]\n"
        "  handoff_api.py list [--to TARGET] [--pending]\n"
        "  handoff_api.py get DOC_ID\n"
        "  handoff_api.py pickup TARGET [--id DOC_ID]\n"
        "  handoff_api.py materialize-jd [--id DOC_ID] [--folder NAME] [--job-app-root PATH]\n"
        "\n"
        "TARGET/SOURCE: cursor | claude | odysseus | hermes\n"
        "\n"
        "create options:\n"
        "  --goal TEXT           Primary objective\n"
        "  --project PATH        Repo or project directory\n"
        "  --todo ID             Related todo id (repeatable)\n"
        "  --session ID          Source Odysseus session id\n"
        "  --context TEXT        Background / decisions (repeatable)\n"
        "  --done TEXT           Completed work (repeatable)\n"
        "  --next TEXT           Next step (repeatable)\n"
        "  --question TEXT       Open question (repeatable)\n"
        "  --file PATH           Read Goal/Context/Done/Next sections from markdown file\n"
        "  --body TEXT           Raw markdown body (appended after generated sections)\n",
        file=sys.stderr,
    )
    return 2


def _dotenv_candidates(project: str = "") -> list[str]:
    candidates: list[str] = []
    if project:
        candidates.append(os.path.join(project, ".env"))
    odysseus_home = os.environ.get("ODYSSEUS_HOME", "").strip()
    if odysseus_home:
        candidates.append(os.path.join(odysseus_home, ".env"))
    candidates.extend(
        [
            r"C:\Users\tylar\code\odysseus\.env",
            os.path.expanduser("~/code/odysseus/.env"),
        ]
    )
    seen: set[str] = set()
    out: list[str] = []
    for path in candidates:
        norm = os.path.normpath(path)
        if norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _try_load_dotenv(path: str) -> None:
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            if not key.startswith("ODYSSEUS_"):
                continue
            val = val.strip().strip('"').strip("'")
            if val and not os.environ.get(key):
                os.environ[key] = val


def _ensure_config(project: str = "") -> tuple[str, str] | None:
    if not os.environ.get("ODYSSEUS_URL") or not os.environ.get("ODYSSEUS_API_TOKEN"):
        for path in _dotenv_candidates(project):
            _try_load_dotenv(path)
    base_url = os.environ.get("ODYSSEUS_URL", "").strip().rstrip("/")
    token = os.environ.get("ODYSSEUS_API_TOKEN", "").strip()
    missing = []
    if not base_url:
        missing.append("ODYSSEUS_URL")
    if not token:
        missing.append("ODYSSEUS_API_TOKEN")
    if missing:
        print(
            f"missing {', '.join(missing)}; load from Odysseus .env or create a Claude Agent token",
            file=sys.stderr,
        )
        return None
    return base_url, token


def _config() -> tuple[str, str] | None:
    return _ensure_config()


def _normalize_agent(name: str) -> str:
    key = name.strip().lower()
    return TARGET_ALIASES.get(key, key)


def _api_request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    config = _config()
    if config is None:
        raise SystemExit(2)
    base_url, token = config

    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith("/api/codex/"):
        print("refusing non-/api/codex path", file=sys.stderr)
        raise SystemExit(2)

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        print(text or f"HTTP {exc.code}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OSError as exc:
        print(f"request failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    if not content.startswith("---\n"):
        return {}, content
    end = content.find("\n---\n", 4)
    if end == -1:
        return {}, content
    block = content[4:end]
    body = content[end + 5 :]
    meta: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        meta[key.strip()] = val.strip()
    return meta, body


def _handoff_title(target: str, title: str) -> str:
    return f"{HANDOFF_TITLE_PREFIX}{target}: {title.strip()}"


def _is_handoff_doc(doc: dict[str, Any]) -> bool:
    title = (doc.get("title") or "").strip()
    return title.startswith(HANDOFF_TITLE_PREFIX)


def _parse_handoff_doc(doc: dict[str, Any]) -> dict[str, Any]:
    content = doc.get("current_content") or doc.get("content") or ""
    meta, body = _parse_frontmatter(content)
    title = doc.get("title") or ""
    target = meta.get("target", "")
    if not target and title.startswith(HANDOFF_TITLE_PREFIX):
        rest = title[len(HANDOFF_TITLE_PREFIX) :]
        target = rest.split(":", 1)[0].strip()
    return {
        "id": doc.get("id"),
        "title": title,
        "source": meta.get("source", ""),
        "target": _normalize_agent(target) if target else "",
        "status": meta.get("status", "pending"),
        "project": meta.get("project", ""),
        "created_at": meta.get("created_at", doc.get("created_at", "")),
        "todo_ids": [t.strip() for t in meta.get("todo_ids", "").split(",") if t.strip()],
        "session_id": meta.get("session_id", doc.get("session_id", "")),
        "body": body.strip(),
        "meta": meta,
    }


def _section(name: str, items: list[str]) -> str:
    if not items:
        return ""
    lines = [f"## {name}", ""]
    for item in items:
        if name == "Next steps":
            lines.append(f"- {item}")
        elif name in ("Context", "Done so far", "Open questions"):
            lines.append(f"- {item}")
        else:
            lines.append(item)
    lines.append("")
    return "\n".join(lines)


def _bootstrap_block(target: str, project: str, env_file: str) -> str:
    project = project.strip()
    env_file = env_file.strip()
    is_windows = platform.system().lower() == "windows"
    lines = ["## Agent bootstrap", ""]

    if target in VALID_TARGETS and env_file:
        if is_windows:
            lines.extend(
                [
                    "```powershell",
                    f'# Load Odysseus credentials for this session',
                    f'Get-Content "{env_file}" | Where-Object {{ $_ -match \'^ODYSSEUS_\' }} | ForEach-Object {{',
                    "  $parts = $_ -split '=', 2; [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1]) }",
                    "```",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "```bash",
                    "# Load Odysseus credentials for this session",
                    f'set -a && source "{env_file}" && set +a',
                    "```",
                    "",
                ]
            )

    if project:
        if is_windows:
            lines.extend([f'```powershell\ncd "{project}"\n```', ""])
        else:
            lines.extend([f"```bash\ncd {json.dumps(project)}\n```", ""])

    if target == "cursor":
        lines.append("In Cursor, run the bootstrap block above, then execute **Next steps**.")
    elif target == "claude":
        lines.append("In Claude Code, run the bootstrap block above, then execute **Next steps**.")
    elif target == "hermes":
        lines.append(
            "In Hermes, run `handoff_api.py list --pending` or say **Pick up handoff**, "
            "then execute **Next steps**."
        )
    elif target == "odysseus":
        lines.append("In Odysseus, read **Goal** and **Next steps** — continue in chat or link the session.")
    lines.append("")
    return "\n".join(lines)


def _build_content(
    *,
    source: str,
    target: str,
    project: str,
    goal: str,
    context: list[str],
    done: list[str],
    next_steps: list[str],
    questions: list[str],
    todo_ids: list[str],
    session_id: str,
    extra_body: str,
    env_file: str,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    frontmatter = [
        "---",
        "handoff_version: 1",
        f"source: {source}",
        f"target: {target}",
        "status: pending",
        f"project: {project}",
        f"created_at: {now}",
    ]
    if todo_ids:
        frontmatter.append(f"todo_ids: {','.join(todo_ids)}")
    if session_id:
        frontmatter.append(f"session_id: {session_id}")
    frontmatter.append("---")
    frontmatter.append("")

    parts = ["\n".join(frontmatter)]
    if goal:
        parts.append(f"## Goal\n\n{goal.strip()}\n")
    if context:
        parts.append(_section("Context", context))
    if done:
        parts.append(_section("Done so far", done))
    if next_steps:
        lines = ["## Next steps", ""]
        for i, step in enumerate(next_steps, start=1):
            lines.append(f"{i}. {step}")
        lines.append("")
        parts.append("\n".join(lines))
    if questions:
        parts.append(_section("Open questions", questions))
    parts.append(_bootstrap_block(target, project, env_file))
    if extra_body.strip():
        parts.append(extra_body.strip())
        parts.append("")
    return "\n".join(parts)


def _default_env_file(project: str) -> str:
    for path in _dotenv_candidates(project):
        if os.path.isfile(path):
            return path
    candidates = _dotenv_candidates(project)
    return candidates[0] if candidates else ""


DEFAULT_JOB_APP_ROOT = os.path.expanduser(r"~\code\notion\Projects\job-application-ops")
JD_SECTION_MARKERS = ("## Full job description", "## Job description")


def _extract_jd_section(body: str) -> str:
    for marker in JD_SECTION_MARKERS:
        idx = body.find(marker)
        if idx != -1:
            return body[idx + len(marker) :].strip()
    return ""


def _folder_slug_from_handoff(parsed: dict[str, Any]) -> str:
    title = parsed.get("title") or ""
    plain = title.split(":", 1)[-1].strip() if ":" in title else title.strip()
    plain = re.sub(r"\s*\(Handshake\s+\d+\)\s*$", "", plain, flags=re.I)
    parts = re.split(r"\s*[—–-]\s*", plain, maxsplit=1)
    company = parts[0].strip() if parts else "Unknown"
    role = parts[1].strip() if len(parts) > 1 else "Role"
    company_slug = re.sub(r"[^A-Za-z0-9]+", "", company) or "Company"
    role_slug = re.sub(r"[^A-Za-z0-9]+", "", role)[:40] or "Role"
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"{company_slug}_{role_slug}_{month}"


def _materialize_jd(parsed: dict[str, Any], job_app_root: str, folder: str | None = None) -> dict[str, Any]:
    body = parsed.get("body") or ""
    jd_text = _extract_jd_section(body)
    if not jd_text:
        raise SystemExit("handoff body has no '## Full job description' section to materialize")

    folder_name = folder or _folder_slug_from_handoff(parsed)
    dest_dir = os.path.join(job_app_root, "positions", "_active", folder_name)
    os.makedirs(dest_dir, exist_ok=True)

    jd_path = os.path.join(dest_dir, "JD.md")
    with open(jd_path, "w", encoding="utf-8") as fh:
        fh.write(jd_text.strip())
        if not jd_text.endswith("\n"):
            fh.write("\n")

    meta_path = os.path.join(dest_dir, "handoff-source.md")
    meta_lines = [
        "# Handoff source",
        "",
        f"- **Odysseus handoff id:** `{parsed.get('id', '')}`",
        f"- **Title:** {parsed.get('title', '')}",
        f"- **Created:** {parsed.get('created_at', '')}",
        "",
        "Agents: read `JD.md` in this folder first. Do not web-search for the JD if this file exists.",
        "To refresh from Odysseus: `handoff_api.py materialize-jd --id "
        f"{parsed.get('id', '')}`",
        "",
    ]
    with open(meta_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(meta_lines))

    return {
        "ok": True,
        "folder": folder_name,
        "jd_path": jd_path,
        "meta_path": meta_path,
        "job_app_root": job_app_root,
    }


def _list_handoffs(to_target: str | None, pending_only: bool, *, include_body: bool = False) -> list[dict[str, Any]]:
    data = _api_request("GET", "/api/codex/documents?search=handoff&limit=50&sort=recent")
    docs = data.get("documents") or data.get("results") or []
    if isinstance(docs, dict):
        docs = docs.get("documents") or list(docs.values())
    handoffs = []
    for doc in docs:
        if not isinstance(doc, dict) or not _is_handoff_doc(doc):
            continue
        if include_body and not (doc.get("current_content") or doc.get("content")):
            doc = _api_request("GET", f"/api/codex/documents/{doc.get('id')}")
            if isinstance(doc, dict) and "document" in doc:
                doc = doc["document"]
        parsed = _parse_handoff_doc(doc)
        if to_target and parsed["target"] != to_target:
            continue
        if pending_only and parsed["status"] != "pending":
            continue
        handoffs.append(parsed)
    return handoffs


def cmd_create(args: argparse.Namespace) -> int:
    target = _normalize_agent(args.target)
    source = _normalize_agent(args.source)
    if target not in VALID_TARGETS:
        print(f"invalid target: {args.target}", file=sys.stderr)
        return 2
    if source not in VALID_TARGETS:
        print(f"invalid source: {args.source}", file=sys.stderr)
        return 2

    extra_body = args.body or ""
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            extra_body = fh.read()

    project = args.project or os.getcwd()
    env_file = args.env_file or _default_env_file(project)
    content = _build_content(
        source=source,
        target=target,
        project=project,
        goal=args.goal or args.title,
        context=args.context or [],
        done=args.done or [],
        next_steps=args.next or [],
        questions=args.question or [],
        todo_ids=args.todo or [],
        session_id=args.session or "",
        extra_body=extra_body,
        env_file=env_file,
    )

    payload = {
        "title": _handoff_title(target, args.title),
        "content": content,
        "language": "markdown",
    }
    if args.session:
        payload["session_id"] = args.session

    result = _api_request("POST", "/api/codex/documents", payload)
    doc_id = result.get("id") or result.get("document_id") or (result.get("document") or {}).get("id")
    pickup_hint = {
        "cursor": f'In Cursor, say: "Pick up handoff {doc_id}" or run handoff_api.py pickup cursor --id {doc_id}',
        "claude": f'In Claude Code, say: "Pick up handoff {doc_id}" or run handoff_api.py pickup claude --id {doc_id}',
        "hermes": f'In Hermes, say: "Pick up handoff {doc_id}" or run handoff_api.py pickup hermes --id {doc_id}',
        "odysseus": f'In Odysseus, open document {doc_id} or say: "Pick up handoff {doc_id}"',
    }
    out = {
        "ok": True,
        "id": doc_id,
        "title": payload["title"],
        "target": target,
        "source": source,
        "project": project,
        "next_action": pickup_hint.get(target, ""),
    }
    if "## Full job description" in content or "## Job description" in content:
        try:
            parsed = _parse_handoff_doc(
                {
                    "id": doc_id,
                    "title": payload["title"],
                    "current_content": content,
                    "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
            job_root = (
                project
                if project and os.path.basename(project) == "job-application-ops"
                else DEFAULT_JOB_APP_ROOT
            )
            out["materialized_jd"] = _materialize_jd(parsed, job_root, None)
        except SystemExit as exc:
            out["materialized_jd_error"] = str(exc)
        except OSError as exc:
            out["materialized_jd_error"] = str(exc)
    print(json.dumps(out, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    to_target = _normalize_agent(args.to) if args.to else None
    handoffs = _list_handoffs(to_target, args.pending, include_body=True)
    rows = []
    for h in handoffs:
        rows.append(
            {
                "id": h["id"],
                "title": h["title"],
                "source": h["source"],
                "target": h["target"],
                "status": h["status"],
                "project": h["project"],
                "created_at": h["created_at"],
            }
        )
    print(json.dumps({"count": len(rows), "handoffs": rows}, indent=2))
    return 0


def cmd_get(doc_id: str) -> int:
    doc = _api_request("GET", f"/api/codex/documents/{urllib.parse.quote(doc_id, safe='')}")
    if isinstance(doc, dict) and "document" in doc:
        doc = doc["document"]
    parsed = _parse_handoff_doc(doc)
    print(json.dumps(parsed, indent=2))
    return 0


def cmd_materialize_jd(args: argparse.Namespace) -> int:
    job_app_root = args.job_app_root or DEFAULT_JOB_APP_ROOT
    if args.id:
        doc = _api_request("GET", f"/api/codex/documents/{args.id}")
        if isinstance(doc, dict) and "document" in doc:
            doc = doc["document"]
        parsed = _parse_handoff_doc(doc)
    else:
        handoffs = _list_handoffs(None, pending_only=False, include_body=True)
        if not handoffs:
            print(json.dumps({"ok": False, "error": "no handoffs found"}))
            return 1
        parsed = handoffs[0]

    result = _materialize_jd(parsed, job_app_root, args.folder)
    print(json.dumps(result, indent=2))
    return 0


def cmd_pickup(args: argparse.Namespace) -> int:
    target = _normalize_agent(args.target)
    if target not in VALID_TARGETS:
        print(f"invalid target: {args.target}", file=sys.stderr)
        return 2

    if args.id:
        parsed = json.loads(json.dumps(_parse_handoff_doc(_api_request("GET", f"/api/codex/documents/{args.id}"))))
    else:
        handoffs = _list_handoffs(target, pending_only=True)
        if not handoffs:
            print(json.dumps({"ok": False, "error": f"no pending handoffs for {target}"}))
            return 1
        parsed = handoffs[0]

    if parsed.get("target") and parsed["target"] != target:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"handoff target is {parsed['target']}, not {target}",
                    "handoff": parsed,
                },
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "handoff": parsed,
                "instructions": (
                    "Execute the Next steps in the handoff body. "
                    "Run the Agent bootstrap block first if Odysseus access or a specific cwd is required."
                ),
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        return _usage()

    parser = argparse.ArgumentParser(prog="handoff_api.py", add_help=False)
    sub = parser.add_subparsers(dest="command")

    create_p = sub.add_parser("create")
    create_p.add_argument("target")
    create_p.add_argument("--from", dest="source", required=True)
    create_p.add_argument("--title", required=True)
    create_p.add_argument("--goal")
    create_p.add_argument("--project")
    create_p.add_argument("--todo", action="append", default=[])
    create_p.add_argument("--session")
    create_p.add_argument("--context", action="append", default=[])
    create_p.add_argument("--done", action="append", default=[])
    create_p.add_argument("--next", action="append", default=[])
    create_p.add_argument("--question", action="append", default=[])
    create_p.add_argument("--file")
    create_p.add_argument("--body")
    create_p.add_argument("--env-file")

    list_p = sub.add_parser("list")
    list_p.add_argument("--to")
    list_p.add_argument("--pending", action="store_true")

    get_p = sub.add_parser("get")
    get_p.add_argument("doc_id")

    pickup_p = sub.add_parser("pickup")
    pickup_p.add_argument("target")
    pickup_p.add_argument("--id")

    mat_p = sub.add_parser("materialize-jd")
    mat_p.add_argument("--id")
    mat_p.add_argument("--folder")
    mat_p.add_argument("--job-app-root")

    args = parser.parse_args(sys.argv[1:])
    if args.command == "create":
        return cmd_create(args)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "get":
        return cmd_get(args.doc_id)
    if args.command == "pickup":
        return cmd_pickup(args)
    if args.command == "materialize-jd":
        return cmd_materialize_jd(args)
    return _usage()


if __name__ == "__main__":
    raise SystemExit(main())
