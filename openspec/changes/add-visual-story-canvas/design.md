## Context

Odysseus UI is a vanilla ESM SPA. Research packs (rp-visual-story-canvas-20260801, rp-e0ae2d998f33) recommend a dual-mode research-and-story graph. Open Design is the artifact/render plane—not the node board.

## Goals / Non-Goals

**Goals:**
- React Flow (xyflow) Vite island with Image / Text / Beat / Research / Prompt / Scene cards
- Renderer-independent domain graph (`GraphNode` / `GraphEdge` / sequenceIndex)
- Paste/upload images; typed edges; outline / storyboard / present views
- Research nodes via `/api/research/*` including session-id hydrate
- Persist under `data/story_canvas/`; Open Design export brief bridge

**Non-Goals (v1):**
- ComfyUI plumbing, realtime multiplayer, full screenplay editor
- Embedding OD Electron Studio inside Odysseus
- Autonomous canvas-mutating agents

## Decisions

### D1: React Flow Vite island
**Chosen:** Source in `apps/story-canvas/`, build into `static/story-canvas/` served by FastAPI.
**Why:** Plan-locked for typed handles/edges; host stays vanilla; island is self-contained.

### D2: Domain graph independent of renderer
**Chosen:** Canonical `GraphNode` / `GraphEdge` JSON; RF `nodes`/`edges` are adapters.
**Why:** Allows outline/storyboard/present (and later moodboard) without content duplication.

### D3: File JSON + optional assets dir
**Chosen:** `data/story_canvas/<id>.json`; large images extracted to `data/story_canvas/assets/<id>/`.
**Why:** Matches deep_research pattern; avoids huge inline dataURLs.

### D4: Open Design as export sidecar
**Chosen:** `POST .../export-od` writes a brief package (Markdown + graph JSON + asset refs); optional handoff path under sibling `open-design` if present.
**Why:** OD owns DESIGN.md / deck / image generation; Odysseus owns the story graph.

## Risks / Trade-offs

- Vite build step before deploy → document `npm run build` in apps/story-canvas.
- Auth required on API → island uses `credentials: 'same-origin'`.
- OD clone is large → export works without clone via downloadable brief.

## Migration Plan

1. Ship RF island replacing vanilla prototype board.
2. Keep `/api/story-canvas` contract stable.
3. Add export-od + templates + print/PDF polish.
4. Archive OpenSpec change when tasks complete.
