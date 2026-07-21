"""Validate tailored job-application artifacts after handoff completes."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from src.handoff_materialize import default_job_app_root

MATCH_PATTERNS = (
    re.compile(r"(?:keyword\s+)?match\s*[:\-]\s*(\d{1,3})\s*%", re.I),
    re.compile(r"match\s+score\s*[:\-]\s*(\d{1,3})", re.I),
    re.compile(r"(\d{1,3})\s*%\s+match", re.I),
)

FABRICATION_PATTERNS = (
    re.compile(r"\b(?:increased|decreased|boosted|grew|improved|reduced)\s+.+\s+by\s+\d{1,3}\s*%", re.I),
    re.compile(r"\b(?:saved|generated|delivered)\s+\$[\d,]+(?:\.\d+)?\b", re.I),
    re.compile(r"\b(?:managed|led|oversaw)\s+\d{2,}\+?\s+(?:people|employees|team members)\b", re.I),
)

REQUIRED_FILES = ("JD.md", "notes.md", "cover-letter.md")
RESUME_JSON_NAME = "tailored-resume.json"
VALIDATION_REPORT_NAME = "validation-report.json"


def resolve_job_folder(record) -> Optional[Path]:
    """Resolve positions/_active/<folder>/ for a job record."""
    slug = (getattr(record, "folder_slug", None) or "").strip()
    jd_path = (getattr(record, "jd_path", None) or "").strip()
    if not slug and jd_path:
        slug = Path(jd_path).parent.name
    if not slug:
        return None
    folder = Path(default_job_app_root()) / "positions" / "_active" / slug
    return folder if folder.is_dir() else folder


def parse_match_percent(notes_text: str) -> Optional[int]:
    for pattern in MATCH_PATTERNS:
        match = pattern.search(notes_text or "")
        if match:
            value = int(match.group(1))
            return max(0, min(100, value))
    return None


def _validate_resume_json(path: Path) -> tuple[bool, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return False, "root must be a JSON object"
    if not any(key in data for key in ("basics", "sections", "work", "metadata")):
        return False, "missing expected resume keys (basics/sections/work/metadata)"
    return True, "resume JSON schema OK"


def _scan_fabrication(*paths: Path) -> tuple[bool, str]:
    hits: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in FABRICATION_PATTERNS:
            found = pattern.search(text)
            if found:
                hits.append(f"{path.name}: {found.group(0)[:80]}")
    if hits:
        return False, "; ".join(hits[:3])
    return True, "no suspicious unconfirmed metrics detected"


def validate_job_folder(folder_path: Path) -> dict[str, Any]:
    """Run validation checks and return a structured validation_report."""
    checks: list[dict[str, Any]] = []
    artifact_paths: dict[str, Optional[str]] = {
        "folder": str(folder_path),
        "jd": None,
        "notes": None,
        "cover_letter": None,
        "pdf": None,
        "docx": None,
        "resume_json": None,
    }

    for name in REQUIRED_FILES:
        path = folder_path / name
        exists = path.is_file()
        key = name.replace(".md", "").replace("-", "_")
        artifact_paths[key if key != "jd" else "jd"] = str(path) if exists else None
        checks.append(
            {
                "name": f"artifact_{name}",
                "passed": exists,
                "detail": "present" if exists else f"missing {name}",
            }
        )

    pdf_path: Optional[Path] = None
    docx_path: Optional[Path] = None
    try:
        for entry in sorted(folder_path.iterdir()):
            lower = entry.name.lower()
            if lower.endswith(".pdf") and pdf_path is None:
                pdf_path = entry
            if lower.endswith(".docx") and docx_path is None:
                docx_path = entry
    except OSError as exc:
        checks.append({"name": "artifact_pdf", "passed": False, "detail": str(exc)})

    has_pdf = pdf_path is not None
    artifact_paths["pdf"] = str(pdf_path) if pdf_path else None
    checks.append(
        {
            "name": "artifact_pdf",
            "passed": has_pdf,
            "detail": pdf_path.name if pdf_path else "no PDF found",
        }
    )

    resume_json = folder_path / RESUME_JSON_NAME
    if resume_json.is_file():
        artifact_paths["resume_json"] = str(resume_json)
        ok, detail = _validate_resume_json(resume_json)
        checks.append({"name": "resume_json_schema", "passed": ok, "detail": detail})

    notes_path = folder_path / "notes.md"
    notes_text = ""
    if notes_path.is_file():
        notes_text = notes_path.read_text(encoding="utf-8", errors="replace")
    match_percent = parse_match_percent(notes_text)

    if docx_path is not None:
        artifact_paths["docx"] = str(docx_path)
        if pdf_path is not None:
            pdf_mtime = pdf_path.stat().st_mtime
            docx_mtime = docx_path.stat().st_mtime
            fresh = pdf_mtime >= docx_mtime
            checks.append(
                {
                    "name": "pdf_freshness",
                    "passed": fresh,
                    "detail": (
                        f"pdf mtime >= docx mtime"
                        if fresh
                        else "PDF older than DOCX — reconvert resume"
                    ),
                }
            )

    cover_path = folder_path / "cover-letter.md"
    fab_ok, fab_detail = _scan_fabrication(notes_path, cover_path)
    checks.append(
        {
            "name": "fabrication_guard",
            "passed": fab_ok,
            "detail": fab_detail,
        }
    )

    required_names = {
        "artifact_JD.md",
        "artifact_notes.md",
        "artifact_cover-letter.md",
        "artifact_pdf",
        "pdf_freshness",
        "resume_json_schema",
    }
    required_checks = [c for c in checks if c["name"] in required_names or c["name"].startswith("artifact_")]
    passed_required = all(c["passed"] for c in required_checks if c["name"] != "fabrication_guard")
    score = sum(1 for c in checks if c["passed"]) / max(len(checks), 1)

    passed = passed_required and match_percent is not None and match_percent >= 70

    return {
        "passed": passed,
        "score": round(score, 3),
        "checks": checks,
        "match_percent": match_percent,
        "artifact_paths": artifact_paths,
    }


def write_validation_report(folder_path: Path, report: dict[str, Any]) -> str:
    path = folder_path / VALIDATION_REPORT_NAME
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    return str(path)


def load_validation_report(path: str) -> Optional[dict[str, Any]]:
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None
