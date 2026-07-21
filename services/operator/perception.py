"""Screen perception — live and recent screen OCR via Screenpipe.

Backs the `screen_look` agent tool. Screen-only: never enables Screenpipe
audio capture (the mic belongs to Clicky / Odysseus voice via the mic lease).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

from services.operator.core import (
    CAP_SCREEN_PERCEPTION,
    degraded_envelope,
    envelope,
    require_capability,
    screenpipe_url,
)

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_MINUTES = 5
MAX_LOOKBACK_MINUTES = 120
LIVE_LOOKBACK_SECONDS = 60  # no-query default: "what's on screen right now"
FRAME_LIMIT = 50
REQUEST_TIMEOUT = 15.0
# Screenpipe `q=` is keyword search — long spoken sentences return zero hits.
MAX_QUERY_WORDS = 4
MAX_QUERY_CHARS = 48


def _sanitize_ocr_query(query: Optional[str]) -> Optional[str]:
    """Compress a spoken utterance into short OCR keywords.

    Passing the full user sentence to Screenpipe filters everything out.
    Keep a few content words; drop filler.
    """
    if not query:
        return None
    raw = " ".join(str(query).split()).strip()
    if not raw:
        return None
    stop = {
        "a", "an", "the", "and", "or", "but", "on", "in", "at", "to", "for", "of",
        "is", "are", "was", "were", "be", "been", "am", "i", "my", "me", "we", "you",
        "what", "whats", "what's", "which", "who", "whom", "whose", "when", "where",
        "why", "how", "can", "could", "would", "should", "please", "just", "like",
        "about", "with", "from", "that", "this", "these", "those", "there", "here",
        "right", "now", "screen", "looking", "look", "see", "saw", "show", "tell",
        "speak", "speaks", "speaking", "running", "locally", "laptop", "minutes",
        "ago", "few", "something", "anything", "stuff", "thing", "things",
    }
    words = [w.strip(".,!?;:\"'()[]{}") for w in raw.split()]
    keep = [w for w in words if w and w.lower() not in stop and len(w) > 1]
    if not keep:
        # Fall back to first few raw tokens if everything was stopwords.
        keep = [w for w in words if w][:MAX_QUERY_WORDS]
    shortened = " ".join(keep[:MAX_QUERY_WORDS]).strip()
    if len(shortened) > MAX_QUERY_CHARS:
        shortened = shortened[:MAX_QUERY_CHARS].rsplit(" ", 1)[0].strip()
    return shortened or None


def _char_budget() -> int:
    try:
        return int(os.environ.get("OPERATOR_PERCEPTION_CHAR_BUDGET") or 8000)
    except ValueError:
        return 8000


def _parse_frames(body: Any) -> List[Dict[str, Any]]:
    """Normalize Screenpipe /search items to {timestamp, app, window, text}."""
    frames: List[Dict[str, Any]] = []
    items = body.get("data") if isinstance(body, dict) else None
    if not isinstance(items, list):
        return frames
    for item in items:
        content = item.get("content") if isinstance(item, dict) else None
        if not isinstance(content, dict):
            continue
        text = (content.get("text") or "").strip()
        if not text:
            continue
        frames.append({
            "timestamp": content.get("timestamp"),
            "app": content.get("app_name"),
            "window": content.get("window_name") or content.get("window_title"),
            "text": text,
        })
    # Newest first; Screenpipe timestamps are ISO strings so string sort works.
    frames.sort(key=lambda f: str(f.get("timestamp") or ""), reverse=True)
    return frames


def _apply_budget(frames: List[Dict[str, Any]], budget: int) -> Dict[str, Any]:
    """Cut at a frame boundary once the character budget is exhausted."""
    kept: List[Dict[str, Any]] = []
    used = 0
    for frame in frames:
        cost = len(frame["text"])
        if kept and used + cost > budget:
            break
        kept.append(frame)
        used += cost
        if used >= budget:
            break
    omitted = len(frames) - len(kept)
    out: Dict[str, Any] = {"frames": kept, "truncated": omitted > 0}
    if omitted > 0:
        out["omitted_frames"] = omitted
        out["truncation_note"] = (
            f"[truncated at frame boundary — {omitted} older frame(s) omitted; "
            "narrow with a query or shorter lookback]"
        )
    return out


def screen_look(query: Optional[str] = None, minutes: Optional[int] = None) -> Dict[str, Any]:
    """Return recent OCR frames, optionally filtered by a text query.

    No arguments → frames from the last 60 seconds ("what's on screen now").
    With a query → default 5-minute lookback, capped at 120 minutes.
    """
    gate = require_capability(CAP_SCREEN_PERCEPTION)
    if gate:
        return gate

    if minutes is not None:
        lookback = timedelta(minutes=max(1, min(int(minutes), MAX_LOOKBACK_MINUTES)))
    elif query:
        lookback = timedelta(minutes=DEFAULT_LOOKBACK_MINUTES)
    else:
        lookback = timedelta(seconds=LIVE_LOOKBACK_SECONDS)

    original_query = (query or "").strip() or None
    query = _sanitize_ocr_query(original_query)

    start_time = (datetime.now(timezone.utc) - lookback).isoformat().replace("+00:00", "Z")
    params: Dict[str, str] = {
        "content_type": "ocr",
        "limit": str(FRAME_LIMIT),
        "start_time": start_time,
    }
    if query:
        params["q"] = query

    url = f"{screenpipe_url()}/search?{parse.urlencode(params)}"
    req = request.Request(url, headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, TimeoutError, OSError) as exc:
        return degraded_envelope(CAP_SCREEN_PERCEPTION, f"screenpipe_error: {exc}")
    except (json.JSONDecodeError, ValueError):
        return degraded_envelope(CAP_SCREEN_PERCEPTION, "screenpipe_bad_response")

    frames = _parse_frames(body)
    data = _apply_budget(frames, _char_budget())
    data["query"] = query
    if original_query and original_query != query:
        data["query_original"] = original_query
        data["query_note"] = "long spoken query shortened to OCR keywords"
    data["lookback_minutes"] = round(lookback.total_seconds() / 60, 2)
    data["window_count"] = len({(f.get("app"), f.get("window")) for f in data["frames"]})
    return envelope(CAP_SCREEN_PERCEPTION, True, data=data)
