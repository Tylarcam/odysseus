## Why

Creators need a visual storytelling board inside Odysseus: paste web images, drop quick text/research as editable context, and connect ideas—without jumping to Flora/Weave/ComfyUI. Research shows a dual-mode gap (spatial explore + narrative structure + linear present) that Odysseus research/library can feed.

## What Changes

- Add **Story Canvas** as a React Flow Vite island built to `/static/story-canvas/` (card nodes, typed edges, outline/storyboard/present).
- Persist projects via `/api/story-canvas/projects` under `data/story_canvas/` (+ assets extraction).
- Rail entry (`rail-story-canvas`) opens an overlay iframe (or new tab).
- Unified composer: Text / Beat / Research / Prompt → cards; Research hydrates from library + session id.
- Open Design export bridge: selection → brief package / DESIGN.md handoff (deck + image first).

## Capabilities

### New Capabilities

- `story-canvas-core`: Project graph persistence, autosave, undo, node/edge model.
- `story-canvas-capture`: Paste/upload images with provenance; unified entry modes.
- `story-canvas-research`: Research nodes backed by Odysseus research APIs + session hydrate.
- `story-canvas-views`: Canvas + outline + storyboard + presentation over one graph.
- `story-canvas-od-bridge`: Export selected subgraph to Open Design / DESIGN.md artifacts.

### Modified Capabilities

- (none)

## Impact

- New: `static/story-canvas/*`, `static/js/storyCanvas.js`, `routes/story_canvas_routes.py`
- Touched: `app.py`, `static/index.html`, `static/app.js`, `src/constants.py`
- Sibling: Open Design clone for Phase 4 export (not required for core board)
