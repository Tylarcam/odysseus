# P0 Spawn Plan — 2026-07-09

One sub-agent per P0. Independent file/port ownership. Parent integrates results into `UNDONE-TASKS.md`.

---

## P0#1 — Archivist stack restart (`e3cc73da`)

**Goal:** `:30001` runs quiet PixelRAG wrapper; health matrix green.

| Step | Action |
|------|--------|
| 1 | Read `deploy/scripts/start-archivist.ps1`, `tools/pixelrag_serve_quiet.py`, `memory_stack.env` only |
| 2 | Probe current ports: `:40001`, `:30001`, `:3030` |
| 3 | Stop stale PixelRAG on `:30001` if present; restart via `start-archivist.ps1` |
| 4 | Confirm serve process uses `pixelrag_serve_quiet` (no `%(req)s` spam) |
| 5 | Health matrix: `GET :40001/health` 200; `:30001` responds; Screenpipe `:3030` if expected |

**Done when:** Quiet wrapper on `:30001`; `:40001` healthy; short report written.  
**Do not:** New features, Clicky, Aether, full transcript ingest.  
**Touch ≤5 files** (prefer 0 code changes — ops only).

---

## P0#2 — Clicky model restart (`abd1c962`)

**Goal:** Worker `:40002` uses `CLICKY_CHAT_MODEL=qwen3.5:4b` from `memory_stack.env`.

| Step | Action |
|------|--------|
| 1 | Read `memory_stack.env`, `deploy/scripts/start-clicky.ps1`, `clicky_integration/clicky_client.py` |
| 2 | Confirm env already has `CLICKY_CHAT_MODEL=qwen3.5:4b` |
| 3 | Restart Clicky via `start-clicky.ps1` |
| 4 | Smoke `POST`/`GET` worker health or `/chat` on `:40002` |
| 5 | Verify logs/response show local qwen, **not** `zai-org/GLM-5.1-FP8` |

**Done when:** `:40002` up + model = qwen3.5:4b.  
**Do not:** Archivist PixelRAG deep dive, Aether, full transcript.  
**Touch ≤5 files.**

---

## P0#3 — CEO brief cron race (`eb3d2499`)

**Goal:** Chron/harvest finishes before CEO brief fires (or brief waits / reschedules).

| Step | Action |
|------|--------|
| 1 | Read `src/task_scheduler.py` around `ceo_brief` (`30 7 * * *`) + any chron/swarm/morning gather tasks |
| 2 | Find race: brief at 07:30 vs harvest that must complete first |
| 3 | Minimal fix: delay brief cron, chain after harvest, or gate brief on harvest readiness |
| 4 | Add/adjust a small test or document the ordering invariant |
| 5 | Touch ≤5 files; prefer `task_scheduler.py` only |

**Done when:** Ordering invariant enforced in code; brief cannot race empty harvest.  
**Do not:** Full ideal-loop rewrite, executive-brief-template wiring (P2), full transcript.

---

## P0#4 — Docker MCP gateway keep-alive (`19470a27`)

**Goal:** Host `:8811` gateway stays up for Odysseus Docker → `host.docker.internal:8811/sse`.

| Step | Action |
|------|--------|
| 1 | Read `scripts/start-docker-mcp-gateway.ps1` |
| 2 | Probe `:8811` (expect 401 = alive) |
| 3 | Start gateway if down; leave durable process |
| 4 | Prefer: document + optional boot hook / scheduled task / note in archivist checklist — **not** a fragile forever-loop in agent |
| 5 | Confirm Odysseus can reach gateway (or document exact reconnect step) |

**Done when:** `:8811` listening; start path documented or wired into a boot script.  
**Do not:** Archivist/Clicky feature work.  
**Touch ≤5 files.**

---

## Ownership (avoid collisions)

| Agent | Owns |
|-------|------|
| A | Archivist ports / `start-archivist.ps1` |
| B | Clicky ports / `start-clicky.ps1` |
| C | `src/task_scheduler.py` |
| D | `scripts/start-docker-mcp-gateway.ps1` + gateway process |

`memory_stack.env` is **read-mostly**; only Agent B may edit Clicky model keys if needed.
