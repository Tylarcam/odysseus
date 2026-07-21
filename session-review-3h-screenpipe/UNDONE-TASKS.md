# Cursor tasks left undone (last 3h) — Screenpipe lens

Source: agent sessions + live/disk probes. Resume: `agent --resume="<id>"`.

## P0 — trust / boot blockers

| # | Task | Project | Session |
|---|------|---------|---------|
| 1 | Restart Screenpipe `:3030` NonInteractive; confirm `/health` | odysseus | `d9b78c4e` |
| 2 | Restart PixelRAG quiet serve `:30001` (no FAISS rebuild) | odysseus | `d9b78c4e` |

## P1 — close open loops

| # | Task | Project | Session |
|---|------|---------|---------|
| 3 | Re-export after capture alive; verify timestamps enter open window | odysseus | `d9b78c4e` |
| 4 | Pass `-NonInteractive` from `start-archivist.ps1` → screenpipe | odysseus | `c5747aed` / P0-1 |
| 5 | Populate `browser_url` / better window title in export → tiles metadata | odysseus | `d9b78c4e` |

## P2 — planned but not built

| # | Task | Project | Session |
|---|------|---------|---------|
| 6 | Align local screen-pipe with accessibility content_type (docs vs fork) | screen-pipe | `d9b78c4e` |
| 7 | Incremental/index-freshness doctor (FAISS age vs newest tile) | odysseus | reviewer add |
| 8 | Optional: meeting-day Screenpipe audio protocol | odysseus | `2f507bb6` |

## Done in-session (not undone — for contrast)

- Screenpipe data-point comprehension brief
- Local STT Docker fix + end-session note
- Voice.ai TTS container rebuild
- Morning archivist export once succeeded (100 rows / 950 tiles)

---

**Suggested next 3:** #1 → #2 → #3.
