"""Sync job-description sections from Odysseus handoff documents to job-application-ops."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

HANDOFF_TITLE_PREFIX = "handoff → "
JD_SECTION_MARKERS = ("## Full job description", "## Job description")


def default_job_app_root() -> str:
    env = os.environ.get("JOB_APPLICATION_OPS_ROOT", "").strip()
    if env:
        return os.path.expanduser(env)
    win_default = r"C:\Users\tylar\code\notion\Projects\job-application-ops"
    if os.path.isdir(win_default):
        return win_default
    return os.path.expanduser("~/code/notion/Projects/job-application-ops")


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    text = content or ""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    block = text[4:end]
    body = text[end + 5 :]
    meta: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        meta[key.strip()] = val.strip()
    return meta, body


def is_handoff_document(title: str) -> bool:
    return (title or "").strip().startswith(HANDOFF_TITLE_PREFIX)


def extract_jd_section(body: str) -> str:
    for marker in JD_SECTION_MARKERS:
        idx = body.find(marker)
        if idx != -1:
            return body[idx + len(marker) :].strip()
    return ""


def folder_slug_from_handoff(title: str) -> str:
    plain = title or ""
    if plain.startswith(HANDOFF_TITLE_PREFIX):
        plain = plain.split(":", 1)[-1].strip()
    plain = re.sub(r"\s*\(Handshake\s+\d+\)\s*$", "", plain, flags=re.I)
    parts = re.split(r"\s*[—–-]\s*", plain, maxsplit=1)
    company = parts[0].strip() if parts else "Unknown"
    role = parts[1].strip() if len(parts) > 1 else "Role"
    company_slug = re.sub(r"[^A-Za-z0-9]+", "", company) or "Company"
    role_slug = re.sub(r"[^A-Za-z0-9]+", "", role)[:40] or "Role"
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"{company_slug}_{role_slug}_{month}"


def materialize_handoff_jd(
    *,
    doc_id: str,
    title: str,
    content: str,
    created_at: str | None = None,
    job_app_root: str | None = None,
    folder: str | None = None,
) -> dict[str, Any]:
    if not is_handoff_document(title):
        raise ValueError("not a handoff document")

    _meta, body = _parse_frontmatter(content)
    jd_text = extract_jd_section(body)
    if not jd_text:
        raise ValueError("handoff has no job description section")

    root = job_app_root or default_job_app_root()
    folder_name = folder or folder_slug_from_handoff(title)
    dest_dir = os.path.join(root, "positions", "_active", folder_name)
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
        f"- **Odysseus handoff id:** `{doc_id}`",
        f"- **Title:** {title}",
        f"- **Created:** {created_at or ''}",
        "",
        "Agents: read `JD.md` in this folder first. Do not web-search for the JD if this file exists.",
        f"To refresh from Odysseus: `handoff_api.py materialize-jd --id {doc_id}`",
        "",
    ]
    with open(meta_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(meta_lines))

    return {
        "ok": True,
        "folder": folder_name,
        "jd_path": jd_path,
        "meta_path": meta_path,
        "job_app_root": root,
    }


def maybe_materialize_handoff_jd(
    *,
    doc_id: str,
    title: str,
    content: str,
    created_at: str | None = None,
    job_app_root: str | None = None,
    folder: str | None = None,
) -> dict[str, Any] | None:
    """Best-effort JD sync. Returns materialize result dict, or None if skipped."""
    if not is_handoff_document(title):
        return None
    if not extract_jd_section(_parse_frontmatter(content)[1]):
        return None
    try:
        result = materialize_handoff_jd(
            doc_id=doc_id,
            title=title,
            content=content,
            created_at=created_at,
            job_app_root=job_app_root,
            folder=folder,
        )
        logger.info(
            "materialized handoff JD doc_id=%s folder=%s path=%s",
            doc_id,
            result.get("folder"),
            result.get("jd_path"),
        )
        return result
    except OSError as exc:
        logger.warning("handoff JD materialize failed for %s: %s", doc_id, exc)
        return None
    except ValueError:
        return None
