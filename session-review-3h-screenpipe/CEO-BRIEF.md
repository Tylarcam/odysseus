# CEO Brief — Last 3 Hours · Screenpipe first pass

_Generated 2026-07-11 10:35 MDT · 4 Cursor sessions in window · 1 Screenpipe-primary · live `:3030` down · gravity: **archivist capture trust**_

## Verdict

First Screenpipe-scoped ops review surfaces a **split brain**: disk still holds a rich OCR export (950 screens / 1113 transcripts; top apps `windows explorer`, `cursor`, `comet`), and unified memory `:40001` is healthy — but **Screenpipe `:3030` and PixelRAG `:30001` are down**, and **zero exported frames carry timestamps inside this 3h window**. You learned the data model; the capture daemon is not currently feeding new signal.

## What moved

| Theme | What happened | State |
|-------|---------------|-------|
| Screenpipe comprehension | Content types, filters, docs vs Odysseus export mapped (`d9b78c4e`) | Shipped |
| Archivist boot (terminal) | Morning `start-archivist.ps1`: screen-only, export 100→78 frames, 950 tiles, FAISS skip, API up | Partial — API still up; capture/serve down |
| Local STT | Docker Whisper path fixed; `/remember` hit archivist (`c5747aed`) | Shipped (voice) |
| Voice.ai TTS | Container rebuild fixed 503 (`2f507bb6`) | Shipped |
| Handshake jobs | Resume/apps (`1063753d`) | Out of scope |

## Live Screenpipe sample (this review)

| Probe | Result |
|-------|--------|
| `GET :3030/health` | **none found** (connection refused) |
| `GET :3030/search?…&start_time=<3h>` | **none found** |
| `GET :3030/activity-summary` | **none found** (endpoint may not exist on local fork) |
| `GET :40001/health` | `{"status":"ok"}` |
| `GET :30001/health` | **none found** |

### Disk export (archivist materialization)

| Metric | Value |
|--------|-------|
| Screenshots | 950 |
| OCR transcripts | 1113 |
| Audio transcripts | **0** (expected — screen-only) |
| Tile metadata with `http` URL | **0 / 950** |
| Captures with timestamp in last 3h | **0** |
| Newest OCR timestamp | 2026-07-11 11:04 UTC (~05:04 MDT) |
| Top `app_name` | windows explorer 463 · cursor 447 · comet 117 · …

**Capture mode (last known boot):** screen-only · OCR `windows-native` · `--disable-audio` · port 3030

## P0 — do these next (trust & boot)

- [ ] **Restart Screenpipe** — `.\deploy\scripts\start-screenpipe.ps1 -NonInteractive` then `/health` `(d9b78c4e)`
- [ ] **Restart PixelRAG quiet** — `:30001` so memory query path can see tiles again `(P0-1 / d9b78c4e)`

## P1 — ship / close loops

- [ ] **Export freshness** — after `:3030` up, re-run `python -m tools.export_screenpipe --limit 50` and confirm timestamps enter the open window
- [ ] **NonInteractive archivist** — nest `-NonInteractive` into `start-archivist.ps1` so mic prompt cannot stall boot `(P0-1-RESULT)`
- [ ] **Wire `browser_url`** into export/metadata (currently always empty → reopen broken)

## P2 — backlog (valuable, not urgent)

- [ ] Upgrade local `screen-pipe` fork toward accessibility / `window_name` / meetings APIs in current docs
- [ ] Use `/activity-summary` (if/when binary supports it) for CEO briefs instead of raw OCR dumps
- [ ] Optional meeting-day: temporary Screenpipe audio with clear “voice apps off” protocol

## Concepts to keep in working memory

- Docs surface ≫ Odysseus export surface (OCR + optional Audio only today)
- Screen-only is intentional — protects Clicky / Odysseus voice
- `app_name` quality is noisy (`windows explorer` often wraps Cursor UI text)
- Empty `url` on all tiles = reopen-by-URL cannot work yet

## Paste-ready prompts (highest leverage)

1. **[Boot]** ``cd C:\Users\tylar\code\odysseus; .\deploy\scripts\start-screenpipe.ps1 -NonInteractive; Start-Sleep 20; Invoke-RestMethod http://127.0.0.1:3030/health; python -m tools.pixelrag_serve_quiet --index-dir ./my_index --tiles-dir ./my_index/tiles --articles-json ./my_index/articles.json --port 30001``
2. **[Export check]** ``python -m tools.export_screenpipe --limit 50; then report rows_fetched, frames_exported, newest transcript timestamp, top 5 app_name``
3. **[URL gap]** ``In tools/export_screenpipe.py + build_tiles.py, map browser_url/window_name when present; leave empty string if absent. Touch ≤3 files. Done when tiles_metadata sample shows non-empty url for a browser hit or explicit none-found note.``

## Missed / reviewer add

- **[Stale FAISS]** Boot log skipped index rebuild (“embedding takes hours”). New morning frames may be on disk/tiles but **not** in the FAISS index — query freshness is a silent lie until `pixelrag_pipeline` runs. `(terminal 15)`
- **[Fork lag]** Official docs advertise accessibility, UI elements, meetings, speakers, tags; local binary ContentType is still OCR|Audio only — briefs must label “docs” vs “this machine.”
- **[Handshake session]** In window but irrelevant; do not burn cluster slots on it.

### Extra opportunities identified in this review

1. One-shot “archivist doctor” script: probe 3030/30001/40001 + newest export age + warn if FAISS older than newest tile
2. Session-ops template section already drafted in comprehension chat — keep using the Screenpipe CEO skeleton

## Session index

| When | Project | Session | Status | ID |
|------|---------|---------|--------|----|
| 10:32 | odysseus | Screenpipe comprehension + ops | Partial | `d9b78c4e` |
| 10:27 | odysseus | Handshake jobs | Out of scope | `1063753d` |
| 08:08 | odysseus | Voice.ai TTS | Shipped | `2f507bb6` |
| 07:44 | odysseus | Local STT (+ archivist adjacent) | Shipped | `c5747aed` |

## Artifacts in this folder

- `mind-graph.html`
- `sessions/*.md`
- `CEO-BRIEF.md`
- `UNDONE-TASKS.md`
- `PROJECT-FILTER.md`
- `LEFT-OFF-CLUSTER.md`
- `README.md`
- `_raw_sessions.json`
