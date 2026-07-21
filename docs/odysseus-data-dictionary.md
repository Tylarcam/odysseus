# Odysseus Data Dictionary / Component Wiki

> Reference for the whole build: what each layer does, what data it holds, which
> endpoints expose it, and how it maps onto the V.A.U.L.T. Command Center HUD.
> Last updated: 2026-07-03.

---

## 1. Architecture at a glance

| Layer | Location | Role |
|-------|----------|------|
| App entrypoint | `app.py` | FastAPI app; registers all routers, serves `static/index.html` as the SPA shell, mounts `/static` |
| Auth | `src/auth_helpers.py`, `AuthMiddleware` in `app.py` | Session cookie (`odysseus_session`), Bearer `ody_*` API tokens, owner scoping (`owner_filter`) |
| Database | `core/database.py` (SQLAlchemy) | All persistent tables (see §3) |
| Routes | `routes/*.py` | One `APIRouter` per feature, registered in `app.py` |
| Domain logic | `src/*.py`, `src/job_pipeline/`, `services/` | Schedulers, pipelines, aggregators |
| Frontend | `static/index.html` + `static/js/*.js` (vanilla ES modules) | Chat-first shell; feature "pages" are overlays/modals managed by `modalManager.js` |

**Frontend auth pattern:** every browser fetch uses `credentials: 'same-origin'`
(session cookie). A global wrapper in `static/app.js` redirects any 401 to `/login`.
No Authorization headers in the SPA; bearer tokens are for external agents only.

---

## 2. Route modules (API surface)

| Module | Prefix | Key endpoints | Data returned |
|--------|--------|---------------|---------------|
| `home_routes.py` | `/api/home` | `GET /cmd-center`, `GET /recent-projects`, `GET /jobs-attention` | Aggregated dashboard payloads (see §5) |
| `note_routes.py` | `/api/notes` | `GET /`, `GET /{id}`, `POST /`, `GET /handoffs`, `POST /{id}/handoff` | Notes/todos with items, labels, pins, due dates, handoff metadata |
| `document_routes.py` | `/api/document(s)` | `GET /documents/library`, `GET /document/{id}`, `PUT /document/{id}` | Documents/artifacts with language, versions, session folder |
| `task_routes.py` | `/api/tasks` | `GET /`, `POST /{id}/run`, `GET /notifications`, `GET /runs/recent` | Scheduled tasks (cron/daily/event), run history, notifications |
| `session_routes.py` | `/api` | `GET /sessions`, `GET /sessions/recent`, `GET /history/{sid}` | Chat sessions + message history |
| `email_routes.py` | `/api/email` | `GET /list`, `GET /read/{uid}`, `POST /send`, `GET /accounts` | IMAP inbox, tags, spam verdicts, scheduled sends |
| `job_routes.py` | `/api/jobs` | `GET /`, `GET /{id}`, `POST /ingest`, `POST /{id}/mark-applied` | Job application pipeline records + event audit trail |
| `voice_routes.py` | `/api/voice` | `GET /stats`, `GET /slo`, `POST /telemetry`, `POST /client-secret` | Realtime voice gateway health + latency SLO histograms |
| `research_routes.py` | `/api/research` | `GET /active`, `POST /start`, `GET /stream/{sid}` (SSE) | Background research jobs + report library |
| `handoff_relay_routes.py` | `/api/handoff-relay` | `GET /pending`, `POST /{doc}/queue|claim|complete` | Cross-agent (Cursor/Claude) handoff relay queue |
| `memory_routes.py` | `/api/memory` | `GET /`, `POST /search`, `GET /timeline` | Long-term memory entries |
| `calendar_routes.py` | `/api/calendar` | `GET /events`, `POST /sync` | CalDAV calendars + events |
| `model_routes.py` | `/api` | `GET /models`, `GET /model-endpoints`, `GET /default-chat` | LLM endpoint configs, local probe results |
| `cookbook_routes.py` | `/api/cookbook`, `/api/model` | `GET /state`, `POST /model/serve`, `GET /gpus` | Local model-serving lifecycle, GPU inventory |
| `stt_routes.py` | `/api/stt` | `GET /stats`, `POST /transcribe` | Speech-to-text providers |
| `transcribe_routes.py` | `/api/transcribe` | `POST /url` | YouTube/video transcription |
| `chat_routes.py` | `/api/chat*` | `POST /api/chat_stream` (SSE) | Core chat streaming |
| `auth_routes.py` | `/api/auth` | `GET /status`, `POST /login` | Auth/session state |
| `diagnostics_routes.py` | `/api/diagnostics` | health probes, `/api/db/stats` | Subsystem health |

Health/liveness (no auth): `GET /api/health`, `GET /api/ready`, `GET /api/version`.

---

## 3. Database tables (`core/database.py`)

| Table | Owner-scoped | Purpose |
|-------|--------------|---------|
| `sessions` / `chat_messages` | yes | Chat sessions and message history |
| `notes` | yes | Keep-style notes/todos; checklist `items` JSON, `label` tags, `pinned`, `due_date`, handoff fields (`handoff_doc_id`, `handoff_target`, `handoff_relay_status`, `handoff_outcome`) |
| `documents` / `document_versions` | yes | Artifacts/canvas docs with language + versioning |
| `scheduled_tasks` / `task_runs` | yes | Automation (morning brief, housekeeping, cookbook serve, webhooks) |
| `job_records` / `job_events` | yes | Job application pipeline (statuses: `email_received` → `ready_to_apply` / `needs_review` …) |
| `memories` | yes | Long-term memory |
| `email_accounts` | yes | IMAP account configs |
| `model_endpoints` | shared | LLM endpoint configs |
| `api_tokens` | n/a | Bearer tokens (`ody_*`) for external agents |
| `calendars` / `calendar_events` | yes | CalDAV sync |
| `webhooks`, `integrations`, `mcp_servers`, `saved_prompts`, `crew_members`, `user_tools`, `gallery_*`, `comparisons`, `signatures`, `editor_drafts` | mixed | Supporting features |

---

## 4. Domain services

| Module | What it does |
|--------|--------------|
| `src/task_scheduler.py` | Background runner for `scheduled_tasks`; executes LLM prompts and builtin actions on schedule |
| `src/job_pipeline/` | Email → job record ingest, dedup, evaluation, tailoring, apply queue, morning brief (`brief.get_jobs_for_brief`) |
| `src/handoff_packet.py` / `handoff_bin.py` / `handoff_relay.py` | Cross-agent handoff docs; `bucket_handoff_notes()` → `{needs_attention, in_progress, done, counts}` |
| `services/voice/metrics.py` | Rolling latency histograms; `slo_summary()` (p50/p95 mic-to-first-audio etc.) |
| `services/home/dashboard.py` | "Recent projects" aggregation (notes + docs grouped by project tag/folder) |
| `services/home/cmd_center.py` | **V.A.U.L.T. aggregator** — builds the whole command-center payload (see §5) |
| `services/search/`, `src/research_handler.py` | Web search providers + deep research runs |

---

## 5. CMD Center contract (`GET /api/home/cmd-center`)

Built by `services/home/cmd_center.py:build_cmd_center()` from live notes, documents,
tasks, sessions, handoff buckets, and the jobs brief. Payload keys:

| Key | Shape | Source |
|-----|-------|--------|
| `title`, `subtitle` | strings | static |
| `status[]` | `{id, label, state}` — states: `online/idle/busy/alive` | tasks + handoff counts |
| `vitals[]` | `{id, label, value, display, delta, spark[], action}` | notes / documents / active tasks / agent-bin attention counts |
| `directives[]` | `{id, kind: note\|task, title, meta, open_items, action}` | pinned/due/checklist notes + active scheduled tasks |
| `documents[]` | `{id, title, tag (MD/PY/…), size, action}` | 8 most recent documents |
| `stage_cards[]` | `{id, label, subtitle, action, target_id}` | morning-report note, plan note, metrics summary |
| `hero` | `{label, title, value, unit, velocity, action, target_id}` | jobs ready → handoffs → directives → notes (first non-zero) |
| `commands[]` | `{id, label, action}` | fixed command deck (notes, email, tasks, agent bin, jobs, library, research, calendar, refresh) |
| `wire[]` | `{ts, text, action, target_id}` | recent notes/docs/handoffs/jobs/chats, newest first |
| `audio` | `{tts, label}` | static (voice standby) |
| `counts` | notes/documents/tasks/sessions/handoffs_attention/jobs_ready/jobs_review | raw counters |

**Actions** the frontend understands (`static/js/cmdCenter.js:_runAction`):
`notes`, `open_note`, `open_doc`, `library`, `tasks`, `open_task`, `agent_bin`,
`email`, `research`, `calendar`, `open_session`, `jobs`, `refresh`.

**Component atlas & display prefs:** Each HUD region (vitals, priority queue, hero,
globe, etc.) is documented in [`vault-cmd-center-component-atlas.md`](vault-cmd-center-component-atlas.md)
(mirror: `CMD_COMPONENT_ATLAS` in `static/js/cmdCenter.js`). Per-user panel visibility
is client-only: gear icon → `localStorage['odysseus-cmd-center-visibility']` (missing
key = visible). Not stored server-side in Phase 1.

---

## 6. Reference image → Odysseus remap

How each region of the reference HUD (the "V.A.U.L.T." creator dashboard) maps to
real Odysseus data:

| Image element | Reference content | Odysseus mapping |
|---------------|-------------------|------------------|
| Title / subtitle | "V.A.U.L.T. — Voice-Activated Unified Logic Terminal" | "V.A.U.L.T. — Odysseus Command Center" |
| Status pills | CORE · IDLE · LINK · ONLINE · RUNNER · ALIVE | Live: RUNNER=active scheduled tasks, IDLE=busy when handoffs need attention |
| Clock | 18:32:37 + date | Local clock, ticks every second |
| System Vitals | YT subs, Instagram, latest video, Claude window | Notes count (+pinned), Documents (+active), Scheduled Tasks (+paused), Agent Bin attention (+in flight) — each with sparkline + delta |
| Directives | Creator todo list | Pinned/due/checklist notes + active scheduled tasks (click to open) |
| Documents | Plan Today / Morning Report files | 8 most recent Odysseus documents with language tag + size |
| Particle sphere | Decorative node network | Canvas 2D particle sphere (decorative, live-rendered) |
| Floating cards | MORNING REPORT / PLAN TODAY / METRICS PULL | Morning brief note or jobs headline / plan note / live counts summary |
| Hero counter | "3,225 VIEWS" + velocity | Jobs ready → handoffs → open directives → notes (first non-zero), animated count-up; velocity = jobs headline or chats/agents summary |
| Command Deck | Metrics Pull, Inbox Brief, Trend Scan… | Notes, Inbox Brief, Tasks, Plan Today, Agent Bin, AM Report, Library, Research, Calendar, Vault Sync — all open real tools |
| Audio I/O | TTS standby / hold space to talk | Voice gateway status (`/api/voice/stats` available for live health) |
| AI Wire | AI news ticker | Live activity feed: recent notes, docs, handoffs, job summaries, chat sessions |
| Transcript button | Video transcript | Recent chat sessions (open session) |

---

## 7. Agentic OS branch map (system-level view)

Visual: `docs/odysseus-system-map.excalidraw` (regenerate with
`python scripts/generate_system_map_excalidraw.py`).

Modeled on the "Agentic OS" layout: **You → Odysseus (the conductor) → branches →
automation layer → tools/integrations**. Odysseus branches:

| Branch | Type | What lives there |
|--------|------|------------------|
| MEMORY | foundation, always on | memories DB, memory search/timeline, AgentMemory relay, saved prompts, mempalace MCP |
| PRODUCTIVITY | foundation, always on | notes/todos, scheduled tasks, calendar (CalDAV), morning brief, home dashboard |
| RESEARCH | capability | deep research (SSE), search providers, Perplexity agent, video transcribe, audio brief |
| CONTENT / DOCS | capability | document library + versions, visual report, gallery, image editor |
| EMAIL / COMMS | capability | IMAP inbox, pollers, scheduled sends, fenced email tools, Gmail GOG bridge |
| JOBS PIPELINE | agency / revenue | email ingest → dedupe → evaluator → tailoring → apply queue + followups |
| VOICE | capability | realtime gateway, voice tools, STT, TTS, SLO metrics |
| AGENT RELAY | cross-agent | handoff packets, agent bin, relay queue, Cursor/Claude/Codex skills, relay watcher |
| MODELS / OPS | per-build, swappable | model endpoints, cookbook serve (local models/GPUs), MCP manager, diagnostics, API tokens |

**Automation layer:** `src/task_scheduler.py` — cron/daily/event triggers, webhooks,
builtin actions.
**Tools & integrations:** Cursor, Claude Code, Codex, MCP servers, IMAP/Gmail,
CalDAV, local models (Ollama/cookbook), OpenAI/Anthropic/Perplexity.

### Gaps vs. the reference Agentic OS

Branches in the reference image with no Odysseus equivalent yet:

- **COMMUNITY** (member onboarding, Q&A digest, comment triage) — no social/audience surface in the build.
- **SALES** (pitch decks, lead enrichment, follow-up cadence) — closest existing piece is the jobs pipeline follow-ups.
- **FINANCE** (books categorizer, tax prep, anomaly scan) — nothing ingests financial data today.
- **CONTENT (creator sense)** (post drafts, carousels, thumbnails) — Odysseus has documents/reports, not a publishing pipeline.

Decision (2026-07-03): map only what exists today; treat the gaps as a business
triage instead. Build order: P1 finance ledger + generalized pipeline records,
P2 sales/CRM branch + weekly business review task, P3 content publishing cadence
+ client onboarding. Full analysis lives in the Cursor canvas
`odysseus-business-triage.canvas.tsx`.

---

## 8. Frontend integration points

| Concern | File / hook |
|---------|-------------|
| CMD Center module | `static/js/cmdCenter.js` (exports `openCmdCenter/closeCmdCenter/toggleCmdCenter`) |
| Nav | sidebar `#tool-cmd-center-btn`, icon rail `#rail-cmd-center` |
| Deep links | `/cmd-center` and `/vault` (pathname routes in `static/app.js` `_routeOpen`) |
| Modal lifecycle | `modalManager.js` (`cmd-center-overlay` registered for minimize/dock) |
| Styles | Injected at runtime as `#cmd-center-styles` (self-contained; not in `style.css`) |
| Tests | `tests/test_home_dashboard.py::test_build_cmd_center_maps_live_odysseus_surfaces` |
