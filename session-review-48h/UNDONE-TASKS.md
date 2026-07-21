# Cursor tasks left undone (last 48h)

Source: agent sessions Jul 7–9 2026. Resume: `agent --resume="<id>"`.

## P0 — trust / boot blockers

| # | Task | Project | Session |
|---|------|---------|---------|
| 1 | ~~Restart archivist stack — quiet PixelRAG on `:30001`~~ **DONE** (`P0-1-RESULT.md`) | odysseus | `e3cc73da` |
| 2 | ~~Restart Clicky worker — qwen3.5:4b~~ **DONE** — model correct; Ollama `:11434` still needed for `/chat` (`P0-2-RESULT.md`) | odysseus | `abd1c962` |
| 3 | ~~Fix CEO brief cron race~~ **DONE** — cron `0 9` + harvest gate (`P0-3-RESULT.md`) | odysseus | `eb3d2499` |
| 4 | ~~Keep Docker MCP gateway alive on host `:8811`~~ **DONE** — listening + Startup install (`P0-4-RESULT.md`) | odysseus | `19470a27` |

## P1 — close open loops

| # | Task | Project | Session |
|---|------|---------|---------|
| 5 | Aether citation pack + Modal yt-dlp metadata parity + redeploy | Aether | `9ddc74a7` |
| 6 | ~~Deep Research — spawn 4 Firecrawl agents~~ → done; brief at `docs/research/perplexity-agent-loop-factory-brief.md` | odysseus | `390950b5` |
| 7 | Implement nav bar / icon-rail tool order personalization | odysseus | `8b5016f5` |
| 8 | Add real URLs to `tiles_metadata.json` for `/reopen` 200 smoke | odysseus | `446eee8e` |
| 9 | CMD Center mobile QA on device + fix auto-spin chip 800ms desync | odysseus | `5c859b5f` |
| 10 | Set Blackboard Top 3 priorities (blank since Jul 3) | odysseus | `ca964913` |
| 11 | Investigate PixelRAG `:30001` health timeout / slow queries (15–50s) | odysseus | `abd1c962` |
| 12 | Verify research export `btn-export` dropdown on mobile | odysseus | `cf4946d0` |

## P2 — planned but not built

| # | Task | Project | Session |
|---|------|---------|---------|
| 13 | Apply HTML-as-review-room pattern to agent deliverables | odysseus | `e2518e4a` |
| 14 | Wire `executive-brief-template.md` into scheduled CEO brief loop | odysseus | `eb3d2499` |
| 15 | Backfill Aether history entries missing video titles | Aether | `9ddc74a7` |
| 16 | Commit traversingSpaces untracked `legacy/`, `qa/`, spec docs | traversingSpaces | `e34d7acf` |
| 17 | Add MCP gateway + port matrix to archivist boot checklist note | odysseus | `19470a27` |

## Done in-session (not undone — for contrast)

- archivist Tasks A–E, 18/18 tests, `/reopen`, quiet PixelRAG wrapper
- Clicky primary overlay wired (`start-clicky.ps1`, worker :40002)
- CMD Center mobile 4-tab bar
- Aether history title via oEmbed (no URL-as-heading)
- Deep Research hero 21:9 banner
- Traversing Spaces `/spaces` timeline pushed (`0a1707a`)
- 168-session Cursor catalog + 3PM reminder in Odysseus
- `session-ops-review` skill authored
- Cursor skill mirror (session-recall, cursor-session-catalog, create-note2ody)
- Docker MCP gateway started and verified

---

**Suggested next 3:** Start Ollama `:11434` (unblocks Clicky `/chat`) → P1 #5 Aether citation pack → P1 #10 Blackboard Top 3.

**P0 cluster (2026-07-09):** #1–#4 all DONE — see `P0-*-RESULT.md`.
