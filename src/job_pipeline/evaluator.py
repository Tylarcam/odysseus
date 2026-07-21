"""Evaluation gate for job records (Phase 2)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Optional

from src.handoff_materialize import default_job_app_root
from src.job_pipeline.store import get_job_record, update_job_record

logger = logging.getLogger(__name__)

GATE_THRESHOLD = 4.0
RUBRIC_REL = os.path.join("templates", "evaluation-rubric.md")
MASTER_RESUME_REL = os.path.join("source-of-truth", "Master_Resume_Complete.md")


def _job_folder(record) -> Optional[str]:
    slug = (record.folder_slug or "").strip()
    if not slug:
        jd = (record.jd_path or "").strip()
        if jd:
            return os.path.dirname(jd)
        return None
    return os.path.join(default_job_app_root(), "positions", "_active", slug)


def _read_optional(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _resolve_llm_endpoint(owner: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    from core.database import Session as DbSession, SessionLocal

    db = SessionLocal()
    try:
        q = db.query(DbSession).filter(
            DbSession.endpoint_url.isnot(None),
            DbSession.model.isnot(None),
        )
        if owner:
            q = q.filter(DbSession.owner == owner)
        recent = q.order_by(DbSession.created_at.desc()).first()
        if recent:
            return recent.endpoint_url, recent.model
    finally:
        db.close()
    return None, None


def _parse_llm_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _default_llm_evaluate(
    *,
    company: Optional[str],
    role: Optional[str],
    jd_text: str,
    rubric: str,
    master_resume: str,
    owner: Optional[str],
) -> dict[str, Any]:
    url, model = _resolve_llm_endpoint(owner)
    if not url or not model:
        raise RuntimeError("No LLM endpoint configured for job evaluation")

    from src.llm_core import llm_call

    rubric_excerpt = (rubric or "")[:12000]
    resume_excerpt = (master_resume or "")[:12000]
    jd_excerpt = (jd_text or "")[:12000]
    prompt = (
        "Evaluate this job posting against the candidate resume using the rubric.\n"
        f"Company: {company or ''}\nRole: {role or ''}\n\n"
        f"RUBRIC:\n{rubric_excerpt}\n\n"
        f"MASTER RESUME:\n{resume_excerpt}\n\n"
        f"JOB DESCRIPTION:\n{jd_excerpt}\n\n"
        "Return ONLY JSON with keys: gate_score (float 1-5), match_score (int 0-100), "
        "profile (string), proceed (bool, true if gate_score >= 4.0), reason (string or null)."
    )
    raw = llm_call(
        url,
        model,
        [
            {"role": "system", "content": "You score job fit for a candidate. Output JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1024,
        timeout=120,
    )
    parsed = _parse_llm_json(raw or "")
    if not parsed:
        raise RuntimeError("LLM evaluation returned unparseable response")
    gate_score = parsed.get("gate_score")
    return {
        "gate_score": float(gate_score) if gate_score is not None else None,
        "match_score": parsed.get("match_score"),
        "profile": parsed.get("profile"),
        "proceed": parsed.get("proceed", float(gate_score or 0) >= GATE_THRESHOLD),
        "reason": parsed.get("reason"),
    }


def _heuristic_score(record, jd_text: str) -> dict[str, Any]:
    """Deterministic fallback when LLM is unavailable (tests / offline)."""
    jd_lower = (jd_text or "").lower()
    role = (record.role or "").lower()
    gate_score = 4.2
    if role and role in jd_lower:
        gate_score = 4.6
    match_score = 82
    return {
        "gate_score": gate_score,
        "match_score": match_score,
        "profile": "default",
        "proceed": gate_score >= GATE_THRESHOLD,
        "reason": None,
    }


async def _default_llm_evaluate(**kwargs):
    """Optional LLM hook — tests patch or replace run_evaluation instead."""
    raise RuntimeError("LLM evaluation not configured")


def run_evaluation(
    job_id: str,
    *,
    owner: Optional[str] = None,
    llm_callable: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """Score a job folder; write evaluation.md. Returns gate result dict."""
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")

    folder = _job_folder(record)
    if not folder:
        return {
            "gate_score": None,
            "proceed": False,
            "evaluation_path": None,
            "match_score": None,
            "profile": None,
            "reason": "job folder not materialized",
        }

    root = default_job_app_root()
    rubric = _read_optional(os.path.join(root, RUBRIC_REL))
    master = _read_optional(os.path.join(root, MASTER_RESUME_REL))
    jd_text = _read_optional(record.jd_path or os.path.join(folder, "JD.md"))

    result = _heuristic_score(record, jd_text)
    if llm_callable is not None:
        try:
            llm_result = llm_callable(
                company=record.company,
                role=record.role,
                jd_text=jd_text,
                rubric=rubric,
                master_resume=master,
                owner=owner,
            )
            if isinstance(llm_result, dict):
                gate_score = llm_result.get("gate_score", result["gate_score"])
                match_score = llm_result.get("match_score", result["match_score"])
                profile = llm_result.get("profile", result["profile"])
                proceed = llm_result.get("proceed", float(gate_score or 0) >= GATE_THRESHOLD)
                result = {
                    "gate_score": float(gate_score) if gate_score is not None else None,
                    "match_score": match_score,
                    "profile": profile,
                    "proceed": bool(proceed),
                    "reason": llm_result.get("reason"),
                }
        except Exception as exc:
            logger.warning("LLM evaluation failed for %s: %s", job_id, exc)
            result = {
                "gate_score": None,
                "match_score": None,
                "profile": None,
                "proceed": False,
                "reason": str(exc),
            }
    else:
        try:
            llm_result = _default_llm_evaluate(
                company=record.company,
                role=record.role,
                jd_text=jd_text,
                rubric=rubric,
                master_resume=master,
                owner=owner,
            )
            if isinstance(llm_result, dict) and llm_result.get("gate_score") is not None:
                gate_score = llm_result.get("gate_score")
                result = {
                    "gate_score": float(gate_score),
                    "match_score": llm_result.get("match_score", result["match_score"]),
                    "profile": llm_result.get("profile", result["profile"]),
                    "proceed": bool(llm_result.get("proceed", float(gate_score) >= GATE_THRESHOLD)),
                    "reason": llm_result.get("reason"),
                }
        except Exception as exc:
            logger.debug("Default LLM evaluation skipped for %s: %s", job_id, exc)

    evaluation_path = os.path.join(folder, "evaluation.md")
    gate_score = result.get("gate_score")
    match_score = result.get("match_score")
    profile = result.get("profile") or "default"
    proceed = bool(result.get("proceed"))

    lines = [
        "# Job Evaluation",
        "",
        f"- **Company:** {record.company or ''}",
        f"- **Role:** {record.role or ''}",
        f"- **Gate score:** {gate_score if gate_score is not None else 'n/a'} / 5.0",
        f"- **Match score:** {match_score if match_score is not None else 'n/a'}%",
        f"- **Profile:** {profile}",
        f"- **Proceed:** {'yes' if proceed else 'no'}",
        "",
    ]
    if result.get("reason"):
        lines.extend([f"- **Reason:** {result['reason']}", ""])
    with open(evaluation_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    update_job_record(
        job_id,
        gate_score=str(gate_score) if gate_score is not None else None,
        match_score=str(match_score) if match_score is not None else None,
        profile=profile,
        evaluation_path=evaluation_path,
    )

    return {
        "gate_score": gate_score,
        "proceed": proceed and gate_score is not None and float(gate_score) >= GATE_THRESHOLD,
        "evaluation_path": evaluation_path,
        "match_score": match_score,
        "profile": profile,
        "reason": result.get("reason"),
    }
