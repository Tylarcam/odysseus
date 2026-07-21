"""AI hero illustration generation for deep research visual reports."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from src.constants import DEEP_RESEARCH_DIR

logger = logging.getLogger(__name__)

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,128}$")
_INFLIGHT_SECONDS = 300


def _research_json_path(session_id: str) -> Optional[Path]:
    if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
        return None
    root = Path(DEEP_RESEARCH_DIR).resolve()
    path = (Path(DEEP_RESEARCH_DIR) / f"{session_id}.json").resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path


def _load_research_json(session_id: str) -> Optional[Dict[str, Any]]:
    path = _research_json_path(session_id)
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _patch_research_json(session_id: str, updates: Dict[str, Any]) -> bool:
    path = _research_json_path(session_id)
    if path is None or not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(updates)
        path.write_text(json.dumps(data), encoding="utf-8")
        return True
    except Exception as e:
        logger.error("Failed to patch research JSON for %s: %s", session_id, e)
        return False


def image_gen_enabled() -> bool:
    try:
        from src.settings import load_settings
        return load_settings().get("image_gen_enabled", True) is not False
    except Exception:
        return True


def build_hero_prompt(
    query: str,
    category: Optional[str] = None,
    synthesized_title: str = "",
) -> str:
    """Build a concise visual prompt from the research question."""
    topic = (synthesized_title or query or "").strip()
    if len(topic) > 200:
        topic = topic[:197] + "..."
    prompt = f"Editorial illustration representing: {topic}. "
    if category:
        prompt += f"Theme: {category}. "
    prompt += (
        "Abstract, professional, cinematic lighting, rich colors, "
        "no text or letters in the image."
    )
    return prompt[:500]


def get_hero_image_meta(session_id: str) -> Dict[str, Any]:
    data = _load_research_json(session_id) or {}
    return {
        "status": data.get("hero_image_status") or "pending",
        "url": data.get("hero_image_url"),
        "prompt": data.get("hero_image_prompt"),
        "error": data.get("hero_image_error"),
        "model": data.get("hero_image_model"),
    }


def _generation_in_flight(data: Dict[str, Any]) -> bool:
    if data.get("hero_image_status") != "pending":
        return False
    started = data.get("hero_image_started_at")
    if not started:
        return False
    try:
        return (time.time() - float(started)) < _INFLIGHT_SECONDS
    except (TypeError, ValueError):
        return False


async def generate_and_persist_hero_image(
    session_id: str,
    entry: dict,
    *,
    force: bool = False,
) -> None:
    """Generate a hero illustration and persist its URL on the research JSON."""
    data = _load_research_json(session_id)
    if data is None:
        return

    if not image_gen_enabled():
        _patch_research_json(session_id, {"hero_image_status": "skipped"})
        return

    if not force:
        status = data.get("hero_image_status")
        if status == "done" and data.get("hero_image_url"):
            return
        if _generation_in_flight(data):
            return

    owner = data.get("owner") or entry.get("owner") or ""
    query = data.get("query") or entry.get("query") or ""
    report_md = data.get("raw_report") or data.get("result") or ""

    synthesized = query
    try:
        from src.visual_report import _extract_report_title
        synthesized, _ = _extract_report_title(str(report_md), query)
    except Exception:
        pass

    prompt = build_hero_prompt(query, data.get("category"), synthesized)

    _patch_research_json(session_id, {
        "hero_image_status": "pending",
        "hero_image_prompt": prompt,
        "hero_image_started_at": time.time(),
        "hero_image_error": None,
    })
    if force:
        _patch_research_json(session_id, {"hero_image_url": None})

    model_line = ""
    try:
        from src.settings import load_settings
        model_line = (load_settings().get("image_model") or "").strip()
    except Exception:
        pass

    content = prompt
    if model_line:
        content += f"\n{model_line}"
    content += "\n1024x1024\nmedium"

    from src.ai_interaction import do_generate_image

    result = await do_generate_image(content, session_id=session_id, owner=owner)

    if result.get("error"):
        _patch_research_json(session_id, {
            "hero_image_status": "error",
            "hero_image_error": result["error"],
            "hero_image_started_at": None,
        })
        return

    image_url = result.get("image_url")
    if not image_url:
        _patch_research_json(session_id, {
            "hero_image_status": "error",
            "hero_image_error": "No image URL returned",
            "hero_image_started_at": None,
        })
        return

    _patch_research_json(session_id, {
        "hero_image_status": "done",
        "hero_image_url": image_url,
        "hero_image_prompt": prompt,
        "hero_image_model": result.get("image_model"),
        "hero_image_started_at": None,
        "hero_image_error": None,
    })
    logger.info("Hero image ready for %s: %s", session_id, image_url)


def kickoff_hero_image(session_id: str, entry: dict, *, force: bool = False) -> None:
    """Fire-and-forget background hero image generation."""
    if entry.get("status") != "done" and not force:
        return

    async def _run() -> None:
        try:
            await generate_and_persist_hero_image(session_id, entry, force=force)
        except Exception as e:
            logger.error("Hero image task crashed for %s: %s", session_id, e, exc_info=True)
            _patch_research_json(session_id, {
                "hero_image_status": "error",
                "hero_image_error": str(e),
                "hero_image_started_at": None,
            })

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())
