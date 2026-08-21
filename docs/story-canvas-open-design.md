# Story Canvas ↔ Open Design

Story Canvas (Odysseus) owns the **story graph**. Open Design owns **brand-grade artifacts** (DESIGN.md, decks, images, HyperFrames).

## Setup

1. Clone sibling (optional but recommended):

```bash
git clone https://github.com/Tylarcam/open-design.git C:/Users/tylar/code/open-design
```

2. Install OD MCP into Cursor / Hermes:

```bash
od mcp install cursor
# or: od mcp install hermes
```

3. In Story Canvas, click **Export OD** — writes:

- `data/story_canvas/exports/<project_id>/brief.md`
- `data/story_canvas/exports/<project_id>/graph.json`
- Handoff copy under `open-design/.od/projects/story-canvas-handoffs/` when the sibling exists, else `data/story_canvas/od_handoff/`

## Artifact targets (v1)

- **Deck** (HTML/PDF/PPTX via OD)
- **Image** (brand still)
- HyperFrame video — deferred

## Build Story Canvas island

```bash
cd apps/story-canvas
npm install
npm run build
```

Served at `/static/story-canvas/` (rail button opens overlay).
