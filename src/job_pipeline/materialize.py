"""Write JD.md to job-application-ops positions/_active/."""

from __future__ import annotations

import os
from typing import Any, Optional

from src.handoff_materialize import default_job_app_root, folder_slug_from_handoff


def materialize_job_jd(
    *,
    job_id: str,
    company: str,
    role: str,
    jd_text: str,
    job_app_root: Optional[str] = None,
    folder: Optional[str] = None,
) -> dict[str, Any]:
    root = job_app_root or default_job_app_root()
    title = f"{company or 'Unknown'} — {role or 'Role'}"
    folder_name = folder or folder_slug_from_handoff(title)
    dest_dir = os.path.join(root, "positions", "_active", folder_name)
    os.makedirs(dest_dir, exist_ok=True)

    jd_path = os.path.join(dest_dir, "JD.md")
    body = (jd_text or "").strip()
    with open(jd_path, "w", encoding="utf-8") as fh:
        fh.write(body)
        if body and not body.endswith("\n"):
            fh.write("\n")

    meta_path = os.path.join(dest_dir, "job-source.md")
    meta_lines = [
        "# Job pipeline source",
        "",
        f"- **Odysseus job id:** `{job_id}`",
        f"- **Company:** {company or ''}",
        f"- **Role:** {role or ''}",
        "",
        "Agents: read `JD.md` in this folder first.",
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
