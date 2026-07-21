#!/usr/bin/env python3
"""Unified personal memory API — PixelRAG + agent memory + MemPalace notes."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import urllib.error
import urllib.request

from tools.agent_memory import search_agent_memory, store_agent_memory
from tools.memory_stack_env import load_memory_stack_env, resolve_path
from tools.mempalace_search import search_notes_index

logger = logging.getLogger("unified_memory_api")

PixelRagSearchFn = Callable[[str, int], List[Dict[str, Any]]]


def _attach_tile_metadata(
    visual_results: List[Dict[str, Any]],
    metadata_path: Path,
) -> List[Dict[str, Any]]:
    if not metadata_path.is_file():
        return visual_results

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return visual_results

    enriched: List[Dict[str, Any]] = []
    for item in visual_results:
        row = dict(item)
        article_id = row.get("article_id")
        tile_id = str(row.get("id") or row.get("tile") or row.get("path") or "")
        tile_name = Path(tile_id).name if tile_id else ""

        meta: Optional[Dict[str, Any]] = None
        if isinstance(metadata, dict):
            if article_id is not None and str(article_id) in metadata:
                meta = metadata[str(article_id)]
            elif tile_name and tile_name in metadata:
                meta = metadata[tile_name]

        if meta:
            row["tile_metadata"] = meta
        enriched.append(row)
    return enriched


def call_pixelrag_search(
    query_text: str,
    k: int = 5,
    *,
    base_url: str | None = None,
    timeout: float | None = None,
) -> List[Dict[str, Any]]:
    """POST to PixelRAG /search endpoint."""
    env = load_memory_stack_env()
    if timeout is None:
        # CPU query embedding through Qwen3-VL can take minutes; keep generous.
        try:
            timeout = float(env.get("PIXELRAG_SEARCH_TIMEOUT", "180"))
        except ValueError:
            timeout = 180.0
    url_base = base_url or env.get("PIXELRAG_SERVE_URL") or "http://localhost:30001"
    if not str(url_base).startswith("http"):
        url_base = f"http://{url_base}"
    endpoint = f"{url_base.rstrip('/')}/search"
    payload = json.dumps(
        {"queries": [{"text": query_text}], "n_docs": k}
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("pixelrag search failed: %s", exc)
        return []

    hits: List[Dict[str, Any]] = []
    if isinstance(body, dict):
        raw_results = body.get("results") or body.get("visual_results") or []
        if raw_results and isinstance(raw_results[0], dict) and "hits" in raw_results[0]:
            for group in raw_results:
                if not isinstance(group, dict):
                    continue
                for hit in group.get("hits") or []:
                    if isinstance(hit, dict):
                        row = dict(hit)
                        row.setdefault("id", row.get("path") or row.get("url"))
                        hits.append(row)
        else:
            hits = [r for r in raw_results if isinstance(r, dict)]
    elif isinstance(body, list):
        hits = [r for r in body if isinstance(r, dict)]
    return hits


def query_personal_memory(
    query_text: str,
    k: int = 5,
    *,
    pixelrag_search: Optional[PixelRagSearchFn] = None,
    metadata_path: Path | None = None,
) -> Dict[str, Any]:
    """Combine visual, agent memory, and notes search results."""
    load_memory_stack_env()
    meta_path = metadata_path or resolve_path("TILES_METADATA_PATH")

    search_fn = pixelrag_search or call_pixelrag_search
    visual_results = search_fn(query_text, k)
    visual_results = _attach_tile_metadata(visual_results, meta_path)

    return {
        "query": query_text,
        "visual_results": visual_results,
        "agent_memory_results": search_agent_memory(query_text, limit=k),
        "notes_results": search_notes_index(query_text, limit=k),
    }


def _build_timeline_events(metadata_path: Path) -> List[Dict[str, Any]]:
    """Read tiles_metadata.json and return screen events for integer keys only.

    The metadata dict is keyed by BOTH str(article_id) AND source filename, with
    the duplicate entries pointing at the same record. Iterating only integer
    keys avoids double-counting. Notes index entries do not carry a usable
    timestamp/mtime field, so notes are not merged (per spec — don't invent
    timestamps).
    """
    if not metadata_path.is_file():
        return []
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(metadata, dict):
        return []

    events: List[Dict[str, Any]] = []
    for key, meta in metadata.items():
        if not (isinstance(key, str) and key.isdigit()):
            continue
        if not isinstance(meta, dict):
            continue
        ts = meta.get("timestamp")
        if not ts:
            continue
        events.append(
            {
                "type": "screen",
                "timestamp": ts,
                "window_title": meta.get("window_title"),
                "url": meta.get("url"),
                "screenpipe_path": meta.get("screenpipe_path"),
                "transcript_path": meta.get("transcript_path"),
                "article_id": meta.get("article_id"),
            }
        )
    return events


def build_timeline(
    *,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    limit: int = 100,
    metadata_path: Path | None = None,
) -> Dict[str, Any]:
    """Return timeline events within [from, to], ascending, capped at limit."""
    load_memory_stack_env()
    meta_path = metadata_path or resolve_path("TILES_METADATA_PATH")

    to_dt_final = to_dt or datetime.now()
    from_dt_final = from_dt or (to_dt_final - timedelta(hours=24))

    events = _build_timeline_events(meta_path)

    def _parse(ts: Any) -> Optional[datetime]:
        if not isinstance(ts, str):
            return None
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return None

    filtered: List[tuple[datetime, Dict[str, Any]]] = []
    for event in events:
        dt = _parse(event.get("timestamp"))
        if dt is None:
            continue
        if from_dt_final <= dt <= to_dt_final:
            filtered.append((dt, event))

    filtered.sort(key=lambda item: item[0])
    capped = [event for _, event in filtered[:limit]]

    return {
        "from": from_dt_final.isoformat(),
        "to": to_dt_final.isoformat(),
        "count": len(capped),
        "events": capped,
    }


def lookup_article_metadata(article_id: int, metadata_path: Path | None = None) -> dict:
    """Return metadata for article_id from tiles_metadata.json.

    Lookup uses ONLY str(article_id) as the key (not source filename).
    Raises LookupError if the article is missing or metadata is unreadable.
    """
    load_memory_stack_env()
    meta_path = metadata_path or resolve_path("TILES_METADATA_PATH")

    if not meta_path.is_file():
        raise LookupError(f"article {article_id} not found")

    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LookupError(f"article {article_id} not found") from exc

    if not isinstance(metadata, dict):
        raise LookupError(f"article {article_id} not found")

    entry = metadata.get(str(article_id))
    if not isinstance(entry, dict):
        raise LookupError(f"article {article_id} not found")

    return entry


def is_openable_url(url: str) -> bool:
    """Return True only for http:// or https:// URLs."""
    if not isinstance(url, str):
        return False
    stripped = url.strip()
    return stripped.startswith("http://") or stripped.startswith("https://")


def open_url_via_browser_harness(url: str) -> None:
    """Open url in a new browser tab via browser-harness CLI stdin."""
    harness = shutil.which("browser-harness")
    if not harness:
        raise RuntimeError("browser-harness not on PATH")

    script = f'new_tab({url!r})\nprint("opened")\n'
    try:
        subprocess.run(
            [harness],
            input=script,
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"browser-harness failed: {exc.stderr or exc.stdout or exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("browser-harness timed out") from exc


def create_app():
    """Starlette app factory (avoids FastAPI/Starlette version skew in some envs)."""
    from starlette.applications import Starlette
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    class RequestIdMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
            request.state.request_id = request_id
            logger.info("request_start id=%s path=%s", request_id, request.url.path)
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info("request_end id=%s status=%s", request_id, response.status_code)
            return response

    async def query_endpoint(request: Request):
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "invalid body"}, status_code=400)

        query_text = str(body.get("query") or "").strip()
        if not query_text:
            return JSONResponse({"error": "query required"}, status_code=400)

        try:
            k = int(body.get("k", 5))
        except (TypeError, ValueError):
            k = 5
        k = max(1, min(20, k))

        rid = getattr(request.state, "request_id", "-")
        logger.info("query id=%s q=%r k=%s", rid, query_text, k)
        return JSONResponse(query_personal_memory(query_text, k))

    async def health(_request: Request):
        return JSONResponse({"status": "ok"})

    async def timeline_endpoint(request: Request):
        from_iso = request.query_params.get("from")
        to_iso = request.query_params.get("to")
        limit_raw = request.query_params.get("limit", "100")

        from_dt: Optional[datetime] = None
        to_dt: Optional[datetime] = None
        if from_iso:
            try:
                from_dt = datetime.fromisoformat(from_iso)
            except ValueError:
                return JSONResponse({"error": "unparseable from"}, status_code=400)
        if to_iso:
            try:
                to_dt = datetime.fromisoformat(to_iso)
            except ValueError:
                return JSONResponse({"error": "unparseable to"}, status_code=400)

        try:
            limit = max(1, int(limit_raw))
        except (TypeError, ValueError):
            limit = 100

        return JSONResponse(
            build_timeline(from_dt=from_dt, to_dt=to_dt, limit=limit)
        )

    async def remember_endpoint(request: Request):
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "invalid body"}, status_code=400)

        summary = str(body.get("summary") or "").strip()
        if not summary:
            return JSONResponse({"error": "summary required"}, status_code=400)

        raw_tags = body.get("tags")
        tags: List[str] = []
        if isinstance(raw_tags, list):
            tags = [str(t) for t in raw_tags]

        source = str(body.get("source") or "").strip()
        if source:
            tags = tags + [f"source:{source}"]

        entry = store_agent_memory(summary, tags=tags or None)
        return JSONResponse(entry, status_code=200)

    async def reopen_endpoint(request: Request):
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "invalid body"}, status_code=400)

        raw_id = body.get("article_id")
        if raw_id is None:
            return JSONResponse({"error": "article_id required"}, status_code=400)
        try:
            article_id = int(raw_id)
        except (TypeError, ValueError):
            return JSONResponse({"error": "invalid article_id"}, status_code=400)

        try:
            meta = lookup_article_metadata(article_id)
        except LookupError:
            return JSONResponse({"error": "article not found"}, status_code=404)

        url = str(meta.get("url") or "").strip()
        if not is_openable_url(url):
            return JSONResponse({"error": "no openable url"}, status_code=422)

        try:
            open_url_via_browser_harness(url)
        except RuntimeError:
            return JSONResponse({"error": "browser-harness unavailable"}, status_code=503)

        return JSONResponse(
            {
                "status": "opened",
                "article_id": article_id,
                "url": url,
                "window_title": meta.get("window_title"),
                "timestamp": meta.get("timestamp"),
                "method": "browser-harness",
            },
            status_code=200,
        )

    app = Starlette(
        routes=[
            Route("/query", query_endpoint, methods=["POST"]),
            Route("/query_personal_memory", query_endpoint, methods=["POST"]),
            Route("/remember", remember_endpoint, methods=["POST"]),
            Route("/timeline", timeline_endpoint, methods=["GET"]),
            Route("/reopen", reopen_endpoint, methods=["POST"]),
            Route("/health", health, methods=["GET"]),
        ],
    )
    app.add_middleware(RequestIdMiddleware)
    return app


def main() -> int:
    import uvicorn

    env = load_memory_stack_env()
    raw_port = env.get("UNIFIED_MEMORY_API_PORT", "40001")
    try:
        port = int(raw_port)
    except ValueError:
        port = 40001

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
