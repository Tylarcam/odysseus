# archivist.ai — External Dependencies

Your local installs (except PixelRAG, which is pip-installed):

| Tool | Path | Boot |
|------|------|------|
| **Screenpipe** | `C:\Users\tylar\code\screen-pipe` | `.\deploy\scripts\start-screenpipe.ps1` (prompts for mic; default screen-only) |
| **Clicky (Windows)** | `C:\Users\tylar\code\clicky-windows` | `.\deploy\scripts\start-clicky.ps1` (starts adapter on `:40002` + `dotnet run`) |
| **Browser Harness** | `C:\Users\tylar\code\browser-harness` | `browser-harness --doctor` then enable Chrome remote debugging |
| **MemPalace** | `C:\Users\tylar\code\MemPalace` | `mempalace --palace C:\Users\tylar\code\MemPalace status` |
| **PixelRAG** | pip package | `pip install "pixelrag[index,serve]"` |

## Links

- Screenpipe: [screenpipe.com](https://screenpipe.com) · [github.com/screenpipe/screenpipe](https://github.com/screenpipe/screenpipe)
- PixelRAG: [github.com/StarTrail-org/PixelRAG](https://github.com/StarTrail-org/PixelRAG) · [pixelrag.ai](https://pixelrag.ai)
- Clicky: [github.com/farzaa/clicky](https://github.com/farzaa/clicky) · Windows port: [clicky-windows](https://github.com/shreshth-s/clicky-windows)
- Browser Harness: [github.com/browser-use/browser-harness](https://github.com/browser-use/browser-harness)
- MemPalace: [millaj.com/mempalace](https://millaj.com/mempalace)

## One-command boot (archivist stack)

```powershell
cd C:\Users\tylar\code\odysseus
.\deploy\scripts\start-archivist.ps1
```

The script sets `PYTHONPATH` to the repo root and runs tools via `python -m tools.*` (fixes `ModuleNotFoundError: No module named 'tools'`). If Screenpipe has no captures yet, export warns and continues; PixelRAG index build is skipped until tiles exist.

This will:
1. Start Screenpipe if not already on `:3030`
2. Export recent captures → `data/archivist/screenpipe/`
3. Build PixelRAG tiles + index, serve on `:30001`
4. Start unified memory API on `:40001`

## Manual terminals (recommended for debugging)

**Terminal 1 — Screenpipe**
```powershell
cd C:\Users\tylar\code\odysseus
.\deploy\scripts\start-screenpipe.ps1
# Press Enter for screen-only (recommended), or y to enable microphone capture
```

**Terminal 2 — PixelRAG**
```powershell
cd C:\Users\tylar\code\odysseus
python -m tools.export_screenpipe
python -m tools.build_tiles
python -m tools.pixelrag_pipeline
python -m tools.pixelrag_serve_quiet --index-dir ./my_index --tiles-dir ./my_index/tiles --articles-json ./my_index/articles.json --port 30001
```

Tiles are written as PixelRAG article dirs (`my_index/tiles/0.png.tiles/`, etc.) with `tiles.json` + `tile_0000.png`. Index build uses `pixelrag chunk`, `pixelrag_embed.embed_cpu`, and `pixelrag_embed.index build` — not `pixelrag index build` on flat PNGs.

**Terminal 3 — Unified API**
```powershell
cd C:\Users\tylar\code\odysseus
python -c "from tools.mempalace_search import build_notes_index; build_notes_index()"
python tools/unified_memory_api.py
```

**Terminal 4 — Clicky Windows** (primary cursor overlay)

One command (checks `:40001`, starts the worker adapter on `:40002`, then `dotnet run`):
```powershell
cd C:\Users\tylar\code\odysseus
.\deploy\scripts\start-clicky.ps1
```

At the console prompts pick **Claude (cloud)** as the model (routes through the adapter; the Ollama models bypass it) and any voice — **Windows TTS (local)** works without the Cloudflare worker. Hold **Ctrl+Alt** to talk once the tray icon appears.

How it is wired (verified against the clicky-windows source, .NET 8 WPF):
- clicky-windows talks to a single `WorkerBaseUrl` (`CompanionManager.cs`), now set to `http://localhost:40002` — the Odysseus adapter `tools/clicky_worker_api.py`.
- Adapter routes: `POST /chat` (Anthropic Messages body in, Anthropic SSE out) is answered from the unified memory API via `POST http://localhost:40001/query`, formatted with `clicky_integration/clicky_client.py`. `POST /transcribe` (Groq Whisper) and `POST /tts` (Voice.ai) are proxied to the upstream Cloudflare worker (`CLICKY_UPSTREAM_WORKER_URL` in `memory_stack.env`, default `https://clicky-proxy.tylarcam.workers.dev`).
- Ports/timeouts: `CLICKY_WORKER_PORT=40002`, `CLICKY_MEMORY_TIMEOUT=30` in `memory_stack.env`.

Manual pieces, if you prefer separate terminals:
```powershell
cd C:\Users\tylar\code\odysseus
.\venv\Scripts\python.exe -m tools.clicky_worker_api   # adapter on :40002
cd C:\Users\tylar\code\clicky-windows\clicky-windows
dotnet run                                             # Clicky overlay
```

Or query memory from Python without the overlay:
```powershell
python -c "from clicky_integration.clicky_client import query_unified_memory, format_overlay_summary; print(format_overlay_summary(query_unified_memory('what was I reading?')))"
```

## Browser Harness

```powershell
pip install -e C:\Users\tylar\code\browser-harness
browser-harness --doctor
```

Enable Chrome remote debugging at `chrome://inspect/#remote-debugging`, then:
```powershell
browser-harness
print(page_info())
PY
```

### POST /reopen (unified memory API)

Re-open a captured screen's URL in Chrome via browser-harness. Looks up `article_id` in `tiles_metadata.json` (integer key only).

```powershell
Invoke-RestMethod -Method POST -Uri http://localhost:40001/reopen `
  -ContentType application/json -Body '{"article_id": 0}'
```

Responses:
- **200** — `{"status":"opened","article_id":N,"url":"...","window_title":"...","timestamp":"...","method":"browser-harness"}`
- **400** — missing or invalid `article_id`
- **404** — article not found in metadata
- **422** — no usable URL (empty or not `http://` / `https://`)
- **503** — browser-harness not on PATH or failed to open tab

Requires `browser-harness` on PATH and Chrome remote debugging enabled.

## MemPalace MCP (optional)

```powershell
mempalace --palace C:\Users\tylar\code\MemPalace mcp
```

## PixelRAG install (only missing piece)

```powershell
pip install "pixelrag[index,serve]"
pixelrag --help
```

First index build downloads `Qwen/Qwen3-VL-Embedding-2B` (~several GB). Plan disk/GPU accordingly.

If you use the Odysseus venv but installed PixelRAG globally, set `PIXELRAG_PYTHON` in `memory_stack.env` to that interpreter (the boot script auto-detects it from the `pixelrag` CLI when possible).

**Quiet serve wrapper:** `pixelrag serve` sets a log format with `%(req)s` at import time, which spams `ValueError: Formatting field not found in record: 'req'` on uvicorn logs. Boot scripts use `python -m tools.pixelrag_serve_quiet` instead: it configures plain logging first, then imports `pixelrag_serve.api.main`. Requires Python 3.12 where `pixelrag[serve]` is installed (not the Odysseus 3.13 venv unless PixelRAG is installed there too).

## Config

All paths live in `memory_stack.env` at the Odysseus repo root.
