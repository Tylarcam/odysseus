# Grounded Build Spec — Personal Web Memory (archivist.ai)

> Status: Phase 1–4 scaffolding implemented in Odysseus repo (2026-07-07).
> Conflict rule: where this spec contradicts code, code wins for paths/values; spec wins for invariants.

## Reality check (audit)

| Claimed gap | Actual state |
|-------------|--------------|
| No automatic capture | Screenpipe repo at `C:/Users/tylar/code/screen-pipe`; export via `tools/export_screenpipe.py` |
| No visual search | PixelRAG via `pip install "pixelrag[index,serve]"`; `pixelrag.yaml` + deploy scripts ready |
| No agent memory store | `tools/agent_memory.py` → `data/archivist/agent_memory.json` |
| MemPalace not wired | Palace at `C:/Users/tylar/code/MemPalace`; search via `tools/mempalace_search.py` |
| Clicky not wired | Windows app at `C:/Users/tylar/code/clicky-windows`; HTTP client in `clicky_integration/clicky_client.py` |
| Browser automation | `C:/Users/tylar/code/browser-harness` (`pip install -e` for global CLI) |

See **`docs/archivist-external-deps.md`** for boot commands and links.

## Layout

```
memory_stack.env          # shared paths
pixelrag.yaml             # PixelRAG index config
tools/
  memory_stack_env.py     # env loader
  build_tiles.py          # Screenpipe → tiles + metadata
  agent_memory.py         # JSON memory store
  mempalace_search.py     # markdown notes index/search
  unified_memory_api.py   # FastAPI :40001 /query
clicky_integration/
  clicky_client.py        # Clicky HTTP client + overlay helpers
deploy/scripts/
  start_pixelrag_local.sh
  start_pixelrag_local.ps1
tests/test_*.py           # per-subsystem tests
```

## Quick start

```powershell
cd C:\Users\tylar\code\odysseus
.\deploy\scripts\start-archivist.ps1
```

Or step-by-step — see `docs/archivist-external-deps.md`.

## Phase gates

- **Phase 1:** `pytest tests/test_build_tiles.py` green; tiles + metadata emitted
- **Phase 2:** agent memory + notes search tests green
- **Phase 3:** unified API combines all three sources; request IDs in logs
- **Phase 4:** Clicky client calls `/query`; overlay summary helper

Full design detail lives in Odysseus note `archivist.ai` (doc `df95dda5-4006-48a1-a07a-5798b46fcec4`).
