"""Story Canvas — persist visual storytelling projects as JSON under data/story_canvas."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from src.auth_helpers import get_current_user
from src.constants import BASE_DIR, STORY_CANVAS_DIR

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_SAFE_FILE = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")


class ProjectCreate(BaseModel):
    title: Optional[str] = "Untitled story"
    payload: Dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class ExportOdBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    node_ids: Optional[List[str]] = Field(default=None, alias="nodeIds")
    design_md: Optional[str] = Field(default="default", alias="designMd")
    handoff: bool = True


class AssetUpload(BaseModel):
    data_url: str
    filename: Optional[str] = None


class StoryResearchBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    count: Optional[int] = Field(default=8, ge=1, le=20)


def _ensure_dir() -> None:
    os.makedirs(STORY_CANVAS_DIR, exist_ok=True)


def _assets_dir(project_id: str) -> str:
    path = os.path.join(STORY_CANVAS_DIR, "assets", project_id)
    os.makedirs(path, exist_ok=True)
    return path


def _exports_dir(project_id: str) -> str:
    path = os.path.join(STORY_CANVAS_DIR, "exports", project_id)
    os.makedirs(path, exist_ok=True)
    return path


def _path(project_id: str) -> str:
    if not _SAFE_ID.match(project_id):
        raise HTTPException(status_code=400, detail="Invalid project id")
    return os.path.join(STORY_CANVAS_DIR, f"{project_id}.json")


def _read(project_id: str) -> Dict[str, Any]:
    path = _path(project_id)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Project not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(doc: Dict[str, Any]) -> None:
    _ensure_dir()
    path = _path(doc["id"])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    payload = doc.get("payload") or {}
    nodes = payload.get("nodes") or []
    return {
        "id": doc["id"],
        "title": doc.get("title") or "Untitled story",
        "owner": doc.get("owner"),
        "node_count": len(nodes),
        "updated_at": doc.get("updated_at"),
        "created_at": doc.get("created_at"),
    }


def _assert_owner(doc: Dict[str, Any], user: Optional[str]) -> None:
    if user and doc.get("owner") and doc.get("owner") != user:
        raise HTTPException(status_code=404, detail="Project not found")


def _build_brief_md(doc: Dict[str, Any], node_ids: Optional[List[str]], design_md: str) -> str:
    payload = doc.get("payload") or {}
    nodes = payload.get("nodes") or []
    edges = payload.get("edges") or []
    if node_ids:
        allow = set(node_ids)
        nodes = [n for n in nodes if n.get("id") in allow]
        edges = [
            e
            for e in edges
            if e.get("from") in allow and e.get("to") in allow
        ]
    lines = [
        f"# Story Canvas brief — {doc.get('title') or 'Untitled'}",
        "",
        f"**Project id:** `{doc['id']}`",
        f"**DESIGN.md:** `{design_md}`",
        "",
        "## Intent",
        "",
        "Generate a brand-grade deck and/or key image from this story graph.",
        "Prefer Open Design skills + active DESIGN.md. Do not invent nodes.",
        "",
        "## Nodes",
        "",
    ]
    for n in sorted(nodes, key=lambda x: x.get("sequenceIndex") or 0):
        lines.append(
            f"### [{n.get('sequenceIndex', 0)}] {n.get('type')} — {n.get('title') or n.get('id')}"
        )
        lines.append("")
        body = (n.get("body") or "").strip()
        if body:
            lines.append(body)
            lines.append("")
        if n.get("src"):
            src = str(n["src"])
            if src.startswith("data:"):
                lines.append("_Image: inline data URL (see graph.json)_")
            else:
                lines.append(f"_Image:_ `{src}`")
            lines.append("")
        if n.get("researchSessionId"):
            lines.append(f"_Research session:_ `{n['researchSessionId']}`")
            lines.append("")
    lines.extend(["## Edges", ""])
    for e in edges:
        lines.append(
            f"- `{e.get('from')}` —{e.get('type') or 'follows'}→ `{e.get('to')}`"
        )
    lines.extend(
        [
            "",
            "## Open Design handoff",
            "",
            "1. Open Open Design Studio (sibling repo `open-design` if cloned).",
            "2. Pick DESIGN.md system matching the brief tag.",
            "3. Target artifacts: **deck** + **image** (HyperFrame later).",
            "4. Keep claims/sources from Research nodes editable in the narrative.",
            "",
        ]
    )
    return "\n".join(lines)


def _open_design_handoff_root() -> Optional[str]:
    """Prefer sibling clone; fall back to data/story_canvas/od_handoff."""
    sibling = os.path.normpath(os.path.join(BASE_DIR, "..", "open-design"))
    if os.path.isdir(sibling):
        target = os.path.join(sibling, ".od", "projects", "story-canvas-handoffs")
        os.makedirs(target, exist_ok=True)
        return target
    fallback = os.path.join(STORY_CANVAS_DIR, "od_handoff")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def setup_story_canvas_routes() -> APIRouter:
    router = APIRouter(prefix="/api/story-canvas", tags=["story-canvas"])

    @router.get("/projects")
    async def list_projects(request: Request) -> Dict[str, List[Dict[str, Any]]]:
        user = get_current_user(request)
        _ensure_dir()
        projects: List[Dict[str, Any]] = []
        for name in os.listdir(STORY_CANVAS_DIR):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(STORY_CANVAS_DIR, name), "r", encoding="utf-8") as f:
                    doc = json.load(f)
            except Exception:
                continue
            if user and doc.get("owner") and doc.get("owner") != user:
                continue
            projects.append(_summary(doc))
        projects.sort(key=lambda p: p.get("updated_at") or 0, reverse=True)
        return {"projects": projects}

    @router.post("/projects")
    async def create_project(body: ProjectCreate, request: Request) -> Dict[str, Any]:
        user = get_current_user(request)
        now = time.time()
        project_id = uuid.uuid4().hex[:12]
        payload = dict(body.payload or {})
        payload["id"] = project_id
        payload["title"] = body.title or payload.get("title") or "Untitled story"
        doc = {
            "id": project_id,
            "title": payload["title"],
            "owner": user,
            "created_at": now,
            "updated_at": now,
            "payload": payload,
        }
        _write(doc)
        return {"id": project_id, "title": doc["title"], "payload": payload}

    @router.get("/projects/{project_id}")
    async def get_project(project_id: str, request: Request) -> Dict[str, Any]:
        user = get_current_user(request)
        doc = _read(project_id)
        _assert_owner(doc, user)
        return {
            "id": doc["id"],
            "title": doc.get("title"),
            "payload": doc.get("payload") or {},
            "updated_at": doc.get("updated_at"),
            "created_at": doc.get("created_at"),
        }

    @router.put("/projects/{project_id}")
    async def update_project(
        project_id: str, body: ProjectUpdate, request: Request
    ) -> Dict[str, Any]:
        user = get_current_user(request)
        doc = _read(project_id)
        _assert_owner(doc, user)
        if body.title is not None:
            doc["title"] = body.title
        if body.payload is not None:
            payload = dict(body.payload)
            payload["id"] = project_id
            payload["title"] = doc["title"]
            doc["payload"] = payload
        doc["updated_at"] = time.time()
        _write(doc)
        return {"id": project_id, "title": doc["title"], "ok": True}

    @router.delete("/projects/{project_id}")
    async def delete_project(project_id: str, request: Request) -> Dict[str, Any]:
        user = get_current_user(request)
        doc = _read(project_id)
        _assert_owner(doc, user)
        os.remove(_path(project_id))
        return {"ok": True, "id": project_id}

    @router.post("/projects/{project_id}/assets")
    async def upload_asset(
        project_id: str, body: AssetUpload, request: Request
    ) -> Dict[str, str]:
        user = get_current_user(request)
        doc = _read(project_id)
        _assert_owner(doc, user)
        raw = body.data_url or ""
        if not raw.startswith("data:") or "," not in raw:
            raise HTTPException(status_code=400, detail="Expected data URL")
        header, b64 = raw.split(",", 1)
        ext = "bin"
        if "image/png" in header:
            ext = "png"
        elif "image/jpeg" in header or "image/jpg" in header:
            ext = "jpg"
        elif "image/webp" in header:
            ext = "webp"
        elif "image/gif" in header:
            ext = "gif"
        name = body.filename or f"{uuid.uuid4().hex[:10]}.{ext}"
        name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)[:128]
        if not name.endswith(f".{ext}"):
            name = f"{name}.{ext}"
        dest = os.path.join(_assets_dir(project_id), name)
        try:
            data = base64.b64decode(b64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid base64") from exc
        with open(dest, "wb") as f:
            f.write(data)
        url = f"/api/story-canvas/projects/{project_id}/assets/{name}"
        return {"url": url}

    @router.get("/projects/{project_id}/assets/{filename}")
    async def get_asset(project_id: str, filename: str, request: Request):
        user = get_current_user(request)
        doc = _read(project_id)
        _assert_owner(doc, user)
        if not _SAFE_FILE.match(filename):
            raise HTTPException(status_code=400, detail="Invalid filename")
        path = os.path.join(_assets_dir(project_id), filename)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(path)

    @router.post("/projects/{project_id}/export-od")
    async def export_od(
        project_id: str, body: ExportOdBody, request: Request
    ) -> Dict[str, Any]:
        user = get_current_user(request)
        doc = _read(project_id)
        _assert_owner(doc, user)
        design = body.design_md or "default"
        brief_md = _build_brief_md(doc, body.node_ids, design)
        export_dir = _exports_dir(project_id)
        brief_path = os.path.join(export_dir, "brief.md")
        graph_path = os.path.join(export_dir, "graph.json")
        with open(brief_path, "w", encoding="utf-8") as f:
            f.write(brief_md)
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(doc.get("payload") or {}, f, ensure_ascii=False, indent=2)

        handoff_dir = None
        if body.handoff:
            root = _open_design_handoff_root()
            if root:
                stamp = time.strftime("%Y%m%d-%H%M%S")
                handoff_dir = os.path.join(root, f"{project_id}-{stamp}")
                os.makedirs(handoff_dir, exist_ok=True)
                Path(handoff_dir, "brief.md").write_text(brief_md, encoding="utf-8")
                Path(handoff_dir, "graph.json").write_text(
                    json.dumps(doc.get("payload") or {}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                Path(handoff_dir, "DESIGN.md.ref").write_text(
                    f"design_md: {design}\n"
                    "Install Open Design MCP: `od mcp install cursor`\n"
                    "Repo: https://github.com/Tylarcam/open-design.git\n",
                    encoding="utf-8",
                )

        return {
            "brief_path": brief_path,
            "graph_path": graph_path,
            "brief_md": brief_md,
            "handoff_dir": handoff_dir,
            "design_md": design,
        }

    @router.post("/research")
    async def story_canvas_research(body: StoryResearchBody, request: Request) -> Dict[str, Any]:
        """Firecrawl web search for Story Canvas right-click research."""
        get_current_user(request)
        query = (body.query or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        from services.search.providers import _get_provider_key, firecrawl_search

        api_key = _get_provider_key("firecrawl") or os.environ.get("FIRECRAWL_API_KEY", "")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Firecrawl is not configured. Set FIRECRAWL_API_KEY in .env "
                    "(or firecrawl_api_key in Admin → Settings), then restart Odysseus "
                    "(docker compose up -d odysseus if using Docker)."
                ),
            )

        try:
            results = firecrawl_search(query, count=body.count)
        except Exception as exc:
            logger.exception("Story canvas Firecrawl search failed")
            raise HTTPException(status_code=502, detail=f"Firecrawl search failed: {exc}") from exc

        if not results:
            raise HTTPException(status_code=502, detail="Firecrawl returned no results")

        return {
            "query": query,
            "results": results,
            "result_count": len(results),
            "provider": "firecrawl",
        }

    return router
