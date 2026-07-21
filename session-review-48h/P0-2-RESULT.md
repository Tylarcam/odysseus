# P0#2 Result — Clicky worker model restart

**Agent:** B  
**Time:** 2026-07-09  
**Status:** DONE (model correct; chat inference blocked by down Ollama)

## Before

| Check | Result |
|-------|--------|
| `:40002` | **Down** — health/status/root all "Unable to connect" |
| Active model | N/A (worker not running) |
| Prior concern | Worker previously associated with `zai-org/GLM-5.1-FP8` / Modal GLM |

## Env confirmed (`memory_stack.env`)

- `CLICKY_WORKER_PORT=40002`
- `CLICKY_CHAT_ENDPOINT_ID=b8local01`
- `CLICKY_CHAT_MODEL=qwen3.5:4b`
- `CLICKY_CHAT_MODE=endpoint`

No env edits required.

## Restart

Full `.\deploy\scripts\start-clicky.ps1` was **not** run end-to-end: it builds/runs the Clicky WPF app in the foreground (`dotnet run`) and would block/require elevation. Worker start matched the script's adapter path:

1. Loaded `memory_stack.env` into process env
2. `PYTHONPATH` = repo root
3. Stopped any listener on `:40002` (none)
4. `Start-Process venv\Scripts\python.exe -m tools.clicky_worker_api` (hidden)

Did **not** touch Archivist / `:30001` / `start-archivist.ps1` / `task_scheduler.py`.

## After

| Check | Result |
|-------|--------|
| `:40002` | **Up** — `GET /health` → `status: ok` |
| `chat_mode` | `endpoint` |
| `chat_model` | **`qwen3.5:4b`** |
| `chat_endpoint_url` | `http://127.0.0.1:11434/v1/chat/completions` |
| GLM-5.1-FP8 | **Not present** in health |

### Smoke

| Probe | Result |
|-------|--------|
| `GET /health` | OK — model `qwen3.5:4b` |
| `POST /mic/claim` + `/mic/release` | OK |
| `POST /chat` (wrong body) | 400 `no user prompt found` (expected) |
| `POST /chat` Anthropic-style messages | Hangs / fails — **Ollama `:11434` unreachable** (`Unable to connect`) |
| curl bad JSON | 400 `invalid json` (route alive) |

## Blockers

1. **Ollama not listening on `:11434`** — health correctly points chat at local Ollama for `qwen3.5:4b`, but inference cannot complete until Ollama is up with that model pulled. This is **not** a GLM/Modal misconfig; env + worker resolution are correct.
2. **Full `start-clicky.ps1`** also launches WPF overlay; for ops-only worker restart, prefer the adapter-only path above (or stop the script after adapter healthy).

## Files touched

**0 code files.** Result doc only: `session-review-48h/P0-2-RESULT.md`.

## Verdict

- Before model: unknown / worker down (historically GLM concern)
- After model: **`qwen3.5:4b`** via endpoint `b8local01` → Ollama URL
- Smoke: health + mic green; chat blocked by down Ollama, not wrong model
