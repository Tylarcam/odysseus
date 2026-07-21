# Agentic Life OS — Build Specification v1.0

> **Status:** Build document. Implementable in 14 days by a senior engineer or a Sonnet-class agent with no additional context beyond this file and the Odysseus repo.
> **Repo:** `c:\Users\tylar\code\odysseus` — Python FastAPI + SQLite (`data/app.db`) + vanilla JS frontend, Docker Compose on Windows.
> **Prime directive:** Maximum 3 human-only decisions per day. Everything else runs itself, is verified before it surfaces, and is metered in dollars.

---

## Section 0 — Reality Check (read this before building anything)

The gap analysis that motivated this spec assumed a greenfield. It is not. The following already exist and MUST be extended, not rebuilt:

| Assumed gap | Actual state |
|---|---|
| "System detects leads but can't close" | Full pipeline exists: `src/job_pipeline/` — ingest → parse → dedup → evaluate (gate 4.0) → tailor via Cursor handoff → validate → apply-package → human submit → `mark_applied`. SQLite tables `job_records` + `job_events`. |
| "No event-driven triggers, cron only" | `src/event_bus.py` + `scheduled_tasks.trigger_type ∈ {schedule, event, webhook}`. Eight events already fire (`email_received`, `document_created`, `memory_added`, etc.). |
| "No model orchestration tier" | Five tier settings exist: `default_*`, `utility_*`, `task_*`, `research_*`, `teacher_*` (+ `vision_model`), with fallback chains, resolved in `src/endpoint_resolver.py`. What's missing is a **routing policy** that uses them, and callers (handoff relay, task scheduler) that ignore the tiers. |
| "No verification subagent" | `_run_verifier_subagent()` exists in `src/agent_loop.py`, opt-in via `agent_verifier_subagent`, currently OFF and uses the same model as the agent. |
| "No cross-agent coordination" | Handoff packets (YAML frontmatter documents), relay state machine (`queued/running/complete/failed`), Agent Bin UI, `scripts/handoff-relay-watcher.ps1` polling `/api/handoff-relay/pending`. Missing: shared blackboard, pickup acks, progress events. |
| "No memory architecture" | Pinned (always-load) vs extended (hybrid vector+BM25 retrieval, top-3/turn) already implemented in `src/chat_processor.py`. Missing: schema on entries, forgetting protocol, single source of truth (JSON `data/memory.json` and SQLite `memories` table coexist unsynced). |
| "No cost tracking" | Only Perplexity has a USD budget (`data/perplexity_usage.json`, `perplexity_daily_budget_usd`). Sessions track token counts, not dollars. |

**Known bugs to fix in passing (Day 1):**

1. **Status mismatch:** after `validate_and_route()`, `job_records.status` stays `validated` while `terminal_status` becomes `ready_to_apply`/`needs_review`. But `get_jobs_for_brief()` (in `src/job_pipeline/brief.py`) filters on `status IN ('ready_to_apply','needs_review')` — ready jobs are invisible to the cmd-center. Fix: filter on `terminal_status`, or make the orchestrator call `transition_to_ready_to_apply()` automatically.
2. **`needs_review` status is never written** by the orchestrator, only `terminal_status`. Same fix resolves it.
3. **`builtin_actions.py` reads SQLite `memories.content`** — the column is `text`. Dead code path; remove or fix during memory consolidation (Section 2).

---

## Section 1 — The Orchestration Kernel

### 1a. Design

One new module owns all model selection. No caller resolves endpoints ad hoc anymore.

**Tier definitions** (map to existing settings prefixes — no new endpoint config needed):

| Tier | Settings prefix | Role | Class of model |
|---|---|---|---|
| `PLAN` | `default_` | Multi-step planning, spec-writing, ambiguous requests | Frontier (Fable/Opus-class) |
| `EXECUTE` | `task_` | Scheduled tasks, handoff relays, pipeline LLM steps | Mid (Sonnet-class) |
| `CLASSIFY` | `utility_` | Routing, scoring, extraction, summarization, yes/no | Cheap (Haiku/GLM-class) |
| `VERIFY` | `verifier_` (**new** settings keys: `verifier_endpoint_id`, `verifier_model`, `verifier_model_fallbacks`) | Independent check of completed work | Mid, **different provider/model than EXECUTE** |
| `RESEARCH` | `research_` | Deep research sessions | Whatever's configured |
| `TEACHER` | `teacher_` | Escalation of last resort | Frontier |

**Routing decision tree** — actual if/then logic, implemented as code, not prompt:

```
route(request) -> Tier:
  if request.kind == "scheduled_task" or request.kind == "handoff_relay":
      tier = EXECUTE
  elif request.kind == "verification":
      tier = VERIFY
  elif request.kind in ("classify", "score", "extract", "summarize", "dedupe"):
      tier = CLASSIFY
  elif request.kind == "research":
      tier = RESEARCH
  elif request.estimated_steps >= 5 or request.requires_planning:
      tier = PLAN
  else:
      tier = EXECUTE

escalate(tier, failure) -> Tier:
  # A tier may escalate exactly once per task. Chain:
  CLASSIFY -> EXECUTE -> PLAN -> TEACHER -> HUMAN (approval queue item, Section 4)
  # VERIFY never escalates; a failed verification re-runs the work at the next tier up.

budget_gate(tier, owner) -> allow | degrade | block:
  spent = ledger.today_usd(owner)                    # Section 7
  cap   = settings["daily_llm_budget_usd"]           # new setting, default 10.0, 0 = uncapped
  if cap == 0 or spent < 0.8 * cap: return allow
  if spent < cap:
      return degrade   # PLAN requests are served at EXECUTE; EXECUTE at CLASSIFY; CLASSIFY unchanged
  return block         # queue an approval item "raise budget or wait until tomorrow"
```

**Fallback chains** stay as-is (`resolve_chat_fallback_candidates`, `*_model_fallbacks`). Escalation is orthogonal: fallback = same tier, different provider (availability); escalation = higher tier (capability).

### 1b. Implementation

- **New:** `src/orchestration/__init__.py`, `src/orchestration/router.py`
  - `class RouteRequest(kind: str, owner: str, estimated_steps: int = 1, requires_planning: bool = False)`
  - `def route(req: RouteRequest) -> ResolvedEndpoint` — calls `endpoint_resolver.resolve_endpoint(prefix, ...)` after tier selection and `budget_gate`.
  - `def escalate(req, prior_tier, failure_reason) -> ResolvedEndpoint | HumanEscalation`
- **Modify:** `src/handoff_relay.py::_resolve_endpoint` and `src/task_scheduler.py::_resolve_defaults` to call `router.route()` instead of "most recent session's model". (Today they silently inherit whatever model was last used in chat — this is the single biggest source of accidental frontier-model spend.)
- **Modify:** `src/agent_loop.py::_run_verifier_subagent` to resolve via `router.route(kind="verification")` so the verifier is a different model than the worker.
- **New settings** in `src/settings.py` `DEFAULT_SETTINGS`: `verifier_endpoint_id`, `verifier_model`, `verifier_model_fallbacks`, `daily_llm_budget_usd: 10.0`.
- Data format: none new — tier is recorded per call in the spend ledger (Section 7, `llm_spend.tier`).

### 1c. First test case

`tests/test_orchestration_router.py`:

```python
def test_handoff_relay_routes_to_execute_tier(monkeypatch):
    # settings: task_model="sonnet-x", default_model="fable-y"
    ep = router.route(RouteRequest(kind="handoff_relay", owner="tylarcam"))
    assert ep.model == "sonnet-x"          # not the frontier default

def test_budget_degrade(monkeypatch):
    # ledger stub: today_usd -> 8.50, cap 10.0  => degrade
    ep = router.route(RouteRequest(kind="chat", owner="tylarcam", requires_planning=True))
    assert ep.tier == "EXECUTE"            # PLAN degraded one tier
```

Proves: tiering is enforced by code, and spend pressure changes routing without human input.

---

## Section 2 — The Memory Architecture

### 2a. Design

**Single source of truth:** SQLite `memories` table. `data/memory.json` becomes a migration source, then read-only backup. ChromaDB stays as the vector index (already `odysseus_memories` collection). MemPalace and AgentMemory remain display/workflow layers — out of scope.

**Schema (extend the existing `memories` table):**

```sql
ALTER TABLE memories ADD COLUMN layer TEXT DEFAULT 'episodic';
   -- 'core'      : always loaded, every agent, every turn (replaces pinned=true)
   -- 'working'   : loaded when its domain tag matches the active task domain
   -- 'episodic'  : retrieved on demand only (hybrid vector+BM25, existing path)
   -- 'archived'  : never retrieved; kept for audit
ALTER TABLE memories ADD COLUMN domain TEXT;          -- 'dissertation'|'jobs'|'consulting'|'relocation'|'system'|NULL
ALTER TABLE memories ADD COLUMN uses INTEGER DEFAULT 0;
ALTER TABLE memories ADD COLUMN last_used_at DATETIME;
ALTER TABLE memories ADD COLUMN expires_at DATETIME;  -- NULL = no expiry
ALTER TABLE memories ADD COLUMN supersedes_id TEXT;   -- newer fact replacing an older one
```

**Loading rules** (deterministic, enforced in `src/chat_processor.py`):

1. `core` — always injected. **Hard cap: 20 entries.** Adding a 21st `core` memory requires archiving one (surfaced as an approval item if an agent tries).
2. `working` — injected when `domain` matches the task's classified domain (the agent loop's `_classify_agent_request()` already produces domains; map them 1:1).
3. `episodic` — existing `_hybrid_retrieve()` top-3, unchanged.

**Forgetting protocol** — a weekly builtin action (`memory_gc`), scheduled like the existing housekeeping tasks:

```
for m in memories where layer != 'core':
    if m.expires_at and m.expires_at < now:                      -> archived
    if m.supersedes_id:                                          -> archive the superseded row
    if m.layer == 'episodic' and m.uses == 0
       and age(m) > 90 days:                                     -> archived
    if m.layer == 'working' and m.last_used_at < now - 30 days:  -> demote to episodic
Nothing is deleted. 'archived' is the terminal layer.
```

**Cross-agent shared context:** memory is already server-side; Cursor and Claude reach it through the existing scoped-token API. Add one endpoint so external agents get the same context bundle Odysseus injects: `GET /api/memory/context-bundle?domain=jobs` → `{core: [...], working: [...], token_estimate: n}`. The handoff packet (Section 5) embeds this bundle's IDs, not its text, so packets stay small and context stays fresh at pickup time.

### 2b. Implementation

- **Modify:** `core/database.py` (`Memory` model + idempotent `ALTER TABLE` migration on startup, same pattern the codebase already uses), `src/memory.py` (`MemoryManager` reads/writes SQLite; keep the JSON import path), `routes/memory_routes.py` (expose `layer`/`domain`; add `/context-bundle`), `src/chat_processor.py` (loading rules above).
- **New:** `action_memory_gc` in `src/builtin_actions.py`, seeded weekly in `TaskScheduler._seed_housekeeping_tasks()`.
- **Migration script:** `scripts/migrate_memory_json_to_sqlite.py` — one-shot, maps `pinned: true` → `layer='core'`, everything else → `episodic`, preserves ids so ChromaDB vectors stay valid. Prints a summary table; does not delete `memory.json`.

### 2c. First test case

`tests/test_memory_layers.py`:

```python
def test_context_bundle_layers(db):
    add_memory(text="Relocating to SF in 60 days", layer="core")
    add_memory(text="MorningAI contact: Chris Curtis", layer="working", domain="jobs")
    add_memory(text="One-off debugging note", layer="episodic")
    bundle = get_context_bundle(owner="tylarcam", domain="jobs")
    texts = [m["text"] for m in bundle["core"] + bundle["working"]]
    assert "Relocating to SF in 60 days" in texts
    assert "MorningAI contact: Chris Curtis" in texts
    assert "One-off debugging note" not in texts   # episodic only via retrieval

def test_gc_archives_stale_episodic(db, frozen_time):
    m = add_memory(text="stale", layer="episodic", created_at=days_ago(120), uses=0)
    run_builtin("memory_gc")
    assert get_memory(m.id).layer == "archived"
```

---

## Section 3 — The Close Engine

### 3a. Design

The pipeline already closes to the last human step. The Close Engine is four additions, not a new system:

**1. Wire email auto-ingest.** `routes/email_pollers.py` currently never calls the job pipeline. Add a CLASSIFY-tier check on each new email: `is_job_lead(email) -> bool` (single cheap LLM call, subject+sender+first 500 chars). If true → `ingest_email_to_job_pipeline(auto_process=True)`. The pipeline's existing dedup (`dedup_key` + `scan-history.tsv`) absorbs repeats.

**2. Fix the terminal transition** (bug #1 in Section 0): `validate_and_route()` calls `transition_to_ready_to_apply()` itself when routing says so, and writes `status='needs_review'` when routing says that. `job_events` already audits every transition.

**3. Autonomous drafting stays where it is** — tailoring is dispatched to Cursor via the existing handoff relay (`tailoring_dispatch.py`); the relay watcher already executes it unattended. No change except tier routing (Section 1).

**4. The approval batch.** New terminal behavior: `on_ready_to_apply()` (in `apply_queue.py`) creates an **approval item** (Section 4) with `category='job_apply'`, payload = `{job_id, company, role, gate_score, match_score, apply_package}`. Approving it queues the browser-harness Handshake workflow (existing `compose_handshake_apply_message()` output) as an `action` scheduled task; the human's only click is the approval. **Auto-submit remains forbidden** — approval IS the submit decision, made once daily in batch, not per-lead ad hoc.

**Extended state machine** (additions in bold; everything else already exists):

```
email_received → parsed → normalized → {archived (dup) | deduped}
deduped → evaluated → {rejected (gate<4.0) | tailoring_started}
tailoring_started → tailoring_complete → validated
validated → {needs_review | ready_to_apply}          ← now real statuses, not just terminal_status
ready_to_apply → **approval_pending** → {**approved → applying → applied** | **declined → archived**}
applied → (existing 7-day follow-up ScheduledTask)
any state → error (retries exhausted) → **approval item, category='pipeline_error'**
```

**Consulting leads** reuse the same tables. `job_records` gets `pipeline TEXT DEFAULT 'job'` (`'job'|'consulting'`). Consulting rows skip tailoring/validation stages (orchestrator branches on `pipeline`): ingest → evaluate (gate = "fit for 60-Min AI Quick Fix at $200?", CLASSIFY tier, same 1–5 rubric shape) → draft outreach (EXECUTE tier, writes `outreach.md` to the job folder) → `ready_to_apply` → approval item `category='consulting_outreach'` → approved = send via existing email tooling → `applied` (= sent).

### 3b. Implementation

- **Modify:** `src/job_pipeline/orchestrator.py` (terminal transitions, `pipeline` branch), `store.py` + `core/database.py` (`pipeline` column), `apply_queue.py` (`on_ready_to_apply` → approval item), `routes/email_pollers.py` (classifier hook), `brief.py` (filter fix).
- **New:** `src/job_pipeline/consulting.py` (`evaluate_consulting_lead`, `draft_outreach`) — mirrors `evaluator.py`'s structure.
- Classifier prompt lives in `prompts/job-lead-classifier.md` (system prompt, returns strict JSON `{"is_lead": bool, "confidence": float}`; below 0.7 confidence → not a lead, log to `job_events`-style audit only).
- Data formats: unchanged (`JD.md`, `evaluation.md`, `apply-package.json` per existing filesystem contract under `job-application-ops/positions/_active/<slug>/`).

### 3c. First test case

`tests/test_close_engine.py` (follows conventions of `tests/test_job_pipeline_phase3.py`):

```python
def test_ready_to_apply_creates_approval_item(db, stub_llm):
    job = seed_job(status="validated", terminal_status="ready_to_apply",
                   gate_score=4.5, match_score=82)
    on_ready_to_apply(job.id)
    items = list_approvals(owner=job.owner, status="pending")
    assert items[0].category == "job_apply"
    assert items[0].payload["job_id"] == job.id
    assert get_job_record(job.id).status == "approval_pending"

def test_approve_queues_handshake_workflow(db):
    item = seed_approval(category="job_apply", payload={"job_id": job.id, ...})
    decide_approval(item.id, decision="approved")
    task = latest_scheduled_task(owner=job.owner)
    assert task.task_type == "action" and "handshake" in task.action
    assert get_job_record(job.id).status == "applying"
```

Proves the exact broken link — "22 leads, 0 applications" — is now one approval click away from closed, end to end.

---

## Section 4 — The 3-Decision Protocol

### 4a. Design

**One queue for every human decision in the system.** Nothing asks the human directly anymore — not the pipeline, not stuck agents, not budget blocks. They all file approval items.

**New table `approvals`:**

```sql
CREATE TABLE approvals (
  id TEXT PRIMARY KEY,             -- uuid
  owner TEXT NOT NULL,
  category TEXT NOT NULL,          -- see category table below
  title TEXT NOT NULL,             -- one line, human-readable
  summary TEXT,                    -- <= 500 chars, written by the requesting agent
  payload TEXT,                    -- JSON, machine-actionable on approve
  source TEXT NOT NULL,            -- 'job_pipeline'|'orchestrator'|'agent_loop'|'ledger'|'skill:<name>'
  risk TEXT DEFAULT 'normal',      -- 'low'|'normal'|'high'
  priority_score REAL,             -- from the arbiter, Section 8
  status TEXT DEFAULT 'pending',   -- 'pending'|'approved'|'declined'|'expired'|'auto_approved'
  decided_at DATETIME, decided_by TEXT,   -- 'human'|'auto:<rule>'
  expires_at DATETIME,             -- default now + 72h
  created_at DATETIME
);
```

**Categories and rules:**

| Category | Example | Auto-approve rule | Never auto |
|---|---|---|---|
| `job_apply` | Submit Handshake application | gate_score ≥ 4.5 AND match ≥ 85 AND `auto_apply_enabled` setting (default **false**) | Default posture: never |
| `consulting_outreach` | Send cold outreach email | Never | ✅ anything sent under Tylar's name to a human |
| `spend` | Raise daily budget / unblock | Never | ✅ money |
| `escalation` | Agent exhausted TEACHER tier | Never | ✅ |
| `pipeline_error` | Job stuck in `error` | Auto-retry once, then surface | — |
| `memory_core_change` | Add/remove `core` memory | Additions with no eviction: auto. Evictions: human | — |
| `schedule_change` | Arbiter wants to move a dissertation block | Never | ✅ time |

**Surfacing — the daily batch:** the morning brief (existing `daily_brief` builtin + the LLM morning-brief task at 07:00) gets a mandatory first section:

```
## Decisions (2 of 3 used this week... )
1. [job_apply] Anthropic — Forward-Deployed Engineer (gate 4.6, match 88) — APPROVE / DECLINE / DEFER
2. [consulting_outreach] Reply to Basecamp Health intro (draft attached) — APPROVE / DECLINE / DEFER
3. [spend] Daily LLM budget hit $10 at 14:00 yesterday — raise to $15? — APPROVE / DECLINE
```

Selection: top 3 pending items by `priority_score` (Section 8). Everything else waits, auto-approves per rules, or expires at 72h (`expired` items are listed in the brief's footer as one line — visibility without decision load). Decisions are batched: the human replies once; a CLASSIFY-tier parse maps the reply to `decide_approval()` calls. The cmd-center gets an Approvals panel mirroring `cmdCenterJobs.js`'s pattern for mid-day access, but the contract is: **the system never expects more than the morning batch.**

### 4b. Implementation

- **New:** `core/database.py` `Approval` model; `src/approvals.py` (`create_approval`, `list_approvals`, `decide_approval` — decide dispatches on `category` to a registered handler, e.g. `job_apply` → the Section 3 flow); `routes/approval_routes.py` (`GET /api/approvals`, `POST /api/approvals/{id}/decide`, `POST /api/approvals/decide-batch`); `static/js/cmdCenterApprovals.js`.
- **Modify:** `src/builtin_actions.py::action_daily_brief` (prepend Decisions section), `prompts/ras-morning-brief.md` (same, for the LLM variant), `services/home/cmd_center.py` (approvals count in hero payload).
- Expiry sweep: piggyback on the scheduler poll loop (it already wakes for due tasks).

### 4c. First test case

`tests/test_approvals.py`:

```python
def test_brief_surfaces_top_three_only(db):
    for i in range(6):
        create_approval(owner="tylarcam", category="job_apply",
                        title=f"job {i}", priority_score=float(i))
    brief = build_decisions_section(owner="tylarcam")
    assert brief.count("APPROVE / DECLINE") == 3
    assert "job 5" in brief and "job 0" not in brief

def test_consulting_outreach_never_auto_approves(db):
    item = create_approval(category="consulting_outreach", ...)
    run_auto_approval_rules(owner="tylarcam")
    assert get_approval(item.id).status == "pending"
```

---

## Section 5 — The Swarm Coordination Layer

### 5a. Design

Keep handoff documents as the **payload** (they work; three agents already speak the format). Add a **blackboard** as the shared state layer the payloads reference.

**New table `blackboard_events`** — append-only, the single log every agent reads and writes:

```sql
CREATE TABLE blackboard_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME NOT NULL,
  agent TEXT NOT NULL,             -- 'odysseus'|'cursor'|'claude'|'system'
  event TEXT NOT NULL,             -- see event enum
  task_ref TEXT,                   -- handoff doc_id | job_id | approval_id | task_id
  task_kind TEXT,                  -- 'handoff'|'job'|'approval'|'scheduled_task'
  detail TEXT                      -- JSON
);
-- event ∈ { claimed, progress, blocked, complete, failed, escalated, spawned }
```

**Message format v2** — extend the existing handoff packet frontmatter (backward compatible; v1 packets still parse):

```yaml
handoff_version: 2
source: odysseus            # existing
target: cursor              # existing
status: pending             # existing lifecycle: pending→queued→running→complete|failed
priority_score: 7.2         # from the arbiter, Section 8 — watcher processes highest first
deadline: 2026-07-09T00:00:00Z   # optional; overdue+unclaimed → escalation approval item
memory_bundle: [mem-uuid-1, mem-uuid-2]   # IDs; agent fetches fresh via /api/memory/context-bundle
verify: true                # if true, completion triggers a VERIFY-tier check before status=complete
on_complete: null           # optional next handoff to auto-create (chaining)
```

**Coordination rules (enforced in `handoff_relay.py`, not by convention):**

1. **Claim before work.** `POST /api/handoff-relay/{doc_id}/claim` (exists) now also writes a `claimed` blackboard event. A packet claimed >`HANDOFF_RELAY_TIMEOUT_HOURS` (exists, default 4) with no `progress` event → auto-requeued once, then `escalation` approval item. This replaces "agents silently stop."
2. **Progress heartbeat.** New `POST /api/handoff-relay/{doc_id}/progress` `{message}` → blackboard event. The watcher script posts one on start and every 30 min.
3. **Verified completion.** When `verify: true`, `complete_external_relay()` holds status at `running`, spawns a VERIFY-tier check ("does the Outcome section satisfy the Goal section? Do referenced files exist?" — for job tailoring this is exactly the existing `validate_job_folder()`), then sets `complete` or `failed` + escalation. Work never surfaces unchecked.
4. **Failure is data.** `failed` requires `detail.reason`. Two failures on the same `task_ref` → automatic escalation approval item. No third silent retry.

Agent Bin (`static/js/agentBin.js`, `src/handoff_bin.py`) becomes the human-readable view of the blackboard — buckets already exist; add the event trail per item.

### 5b. Implementation

- **New:** `BlackboardEvent` model in `core/database.py`; `src/blackboard.py` (`log_event`, `recent_events`, `events_for(task_ref)`); `GET /api/blackboard?since=&task_ref=` in `routes/handoff_relay_routes.py`.
- **Modify:** `src/handoff_relay.py` (claim/complete/scan_stuck write events; verify hook; requeue-then-escalate), `src/handoff_packet.py` + `static/js/handoff.js` + `integrations/claude/skills/handoff/scripts/handoff_api.py` (v2 fields — three copies of the builder exist; change all three, per the packet-format duplication), `scripts/handoff-relay-watcher.ps1` (progress posts, priority ordering).
- The watcher stays a poller. Do not build a message queue; SQLite + 60s polling is correct at this scale.

### 5c. First test case

`tests/test_blackboard.py`:

```python
def test_claim_and_stall_escalates(db, frozen_time):
    doc = create_handoff(target="cursor", verify=False)
    claim_external_relay(doc.id, agent="cursor")
    assert last_event(doc.id).event == "claimed"
    frozen_time.tick(hours=5)          # past HANDOFF_RELAY_TIMEOUT_HOURS, no progress
    scan_stuck_relays()
    assert last_event(doc.id).event in ("spawned", "escalated")  # requeue once
    frozen_time.tick(hours=5)
    scan_stuck_relays()
    assert list_approvals(category="escalation")[0].payload["task_ref"] == doc.id

def test_verified_completion_gates_status(db, stub_verifier_fail):
    doc = create_handoff(target="cursor", verify=True)
    claim_external_relay(doc.id, agent="cursor")
    complete_external_relay(doc.id, outcome="done", status="complete")
    assert relay_status(doc.id) == "failed"     # verifier said no
```

---

## Section 6 — The Skill Upgrade Path

### 6a. Design

Skills stay as `SKILL.md` files (`data/skills/<category>/<name>/SKILL.md` — format in `services/memory/skill_format.py`). Add an optional `machine:` block to frontmatter. Skills without it behave exactly as today (linear injection), so this is non-breaking.

**State machine format:**

```yaml
machine:
  states: [start, <task states...>, done, failed, escalated]
  transitions:
    - from: start
      do: "<step instruction>"
      on_success: <state>
      on_failure: <state>          # omit → failed
      max_retries: 1               # optional
  escalate_to: approval            # 'approval' | 'teacher' | 'handoff:cursor'
```

The agent loop, when a `machine:` skill is invoked (slash-invoke or injection), pins the current state into the prompt and only presents the current transition's instruction — not the whole procedure. State advances are recorded to the blackboard (`task_kind='skill'`).

**The five upgrades:**

| Skill | Current | State machine |
|---|---|---|
| `youtube-ceo-brief` (published, 38 uses) | Linear, works | `start → fetch_transcript → summarize → save_note → done`. `fetch_transcript` failure (transcription API down) → retry once → `failed` + note stub with the URL, never a hallucinated summary. |
| `job-pipeline-agent` (draft) | **Retire the procedure.** It describes a note-based tracker that diverged from the real SQLite pipeline. | Rewrite as a thin operator manual over `process_job_application` tool actions (`ingest/evaluate/status/apply_package/mark_applied`). States mirror `job_records.status` — the DB is the state machine; the skill just reads it. Mark `published` once tests in Section 3 pass. |
| `daily-brief-and-fruit-ledger` (×2 drafts) | Duplicates | Delete `-2`. Split the survivor: brief generation now belongs to Section 4's brief builder; the skill becomes the **Fruit Ledger** recorder: `start → collect_revenue_events (read ledger, Section 7) → collect_spend → compute_ratio → append_ledger_note → done`. On missing ledger data → `escalated: approval` ("ledger has no entries — is instrumentation broken?"). |
| `swarm-health-scan` (draft) | Vague scan | `start → read_blackboard (last 24h) → detect (stalled: claimed w/o progress >4h; contradictions: same task_ref claimed by 2 agents; loops: >3 spawned events same ref) → file_findings (escalation approval items) → done`. Runs as a scheduled `llm` task nightly at 22:00, EXECUTE tier. |
| `problem-statement` (published) | Fine | Leave linear. Not everything needs a machine. |

### 6b. Implementation

- **Modify:** `services/memory/skill_format.py` (parse/serialize `machine:`), `src/agent_loop.py` (state-pinned prompt assembly for machine skills; advance-state on transition markers in the agent's output — a strict line `STATE: <name>` the prompt instructs it to emit), `src/blackboard.py` hookup.
- **Modify:** the four `SKILL.md` files listed; delete `data/skills/productivity/daily-brief-and-fruit-ledger-2/`.
- The existing skill audit machinery (`audit_skills` builtin, `_usage.json` verdicts) applies unchanged — machine skills just have more auditable structure.

### 6c. First test case

`tests/test_skill_machines.py`:

```python
def test_machine_skill_pins_single_transition(skills_manager):
    skill = load_skill("swarm/swarm-health-scan")
    prompt = build_skill_prompt(skill, state="detect")
    assert "read_blackboard" not in prompt          # past state hidden
    assert "stalled" in prompt                      # current instruction shown

def test_failure_transition(skills_manager, db):
    advance = apply_transition(skill, state="fetch_transcript", outcome="failure")
    assert advance.state == "fetch_transcript" and advance.retry == 1   # retry once
    advance = apply_transition(skill, state="fetch_transcript", outcome="failure")
    assert advance.state == "failed"
    assert last_blackboard_event(task_kind="skill").event == "failed"
```

---

## Section 7 — The Financial Instrumentation

### 7a. Design

Two tables, one price file, one ratio.

```sql
CREATE TABLE llm_spend (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME NOT NULL,
  owner TEXT NOT NULL,
  agent TEXT NOT NULL,             -- 'odysseus'|'cursor-relay'|'claude-relay'|'scheduler'|'verifier'
  tier TEXT,                       -- PLAN|EXECUTE|CLASSIFY|VERIFY|RESEARCH|TEACHER
  provider TEXT, model TEXT,
  task_ref TEXT, task_kind TEXT,   -- same convention as blackboard_events
  input_tokens INTEGER, output_tokens INTEGER,
  usd REAL                         -- NULL if model not in price table (local models = 0.0)
);

CREATE TABLE revenue_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME NOT NULL,
  owner TEXT NOT NULL,
  source TEXT NOT NULL,            -- 'consulting'|'upwork'|'salary'|'product'|'other'
  description TEXT,
  amount_usd REAL NOT NULL,
  approval_id TEXT                 -- entered via approval flow or manually
);
```

**Price table:** `data/model_prices.json` — `{ "<provider>/<model-substring>": {"in_per_mtok": 3.0, "out_per_mtok": 15.0} }`. Manually maintained; unknown models log tokens with `usd=NULL` and the weekly report flags them. Local/Ollama models: `0.0`. (Perplexity's existing `data/perplexity_usage.json` budget stays; its calls also log here for the unified view.)

**Capture point:** one place — `src/llm_core.py` already surfaces provider `usage` in stream events, and `stream_llm_with_fallback()` is the choke point every call passes through. Add a post-call hook `ledger.record(usage, context)`. Context (`agent`, `tier`, `task_ref`) threads down from the router (Section 1) — this is why routing had to centralize first.

**The counter for the loop** (money → compute → leverage → money):

```
weekly_ratio = revenue_7d / max(spend_7d, 0.01)
ratio > 5   → headroom: arbiter (Section 8) may raise daily_llm_budget_usd via a `spend` approval item
1 ≤ ratio ≤ 5 → steady state, no action
ratio < 1 for 2 consecutive weeks → arbiter downweights non-revenue agent work;
                                    brief shows "compute is outrunning income" warning
```

Surfaced in: morning brief footer (`spend yesterday: $X · revenue this week: $Y · ratio: Z`), cmd-center Fruit Ledger panel (replacing the current document link), weekly rollup appended by the Fruit Ledger skill (Section 6).

### 7b. Implementation

- **New:** models in `core/database.py`; `src/ledger.py` (`record`, `today_usd`, `weekly_summary`, `ratio`); `routes/ledger_routes.py` (`GET /api/ledger/summary`, `POST /api/ledger/revenue`); `data/model_prices.json` seeded with current providers from the `model_endpoints` table.
- **Modify:** `src/llm_core.py` (hook), `src/orchestration/router.py` (`budget_gate` reads `ledger.today_usd`), `services/home/cmd_center.py` + `static/js/cmdCenter.js` (panel), brief builders (footer line).
- Revenue entry paths: manual API/UI, plus `decide_approval` on a consulting item can prompt "record expected revenue?" — but revenue rows are always human-confirmed numbers, never LLM-estimated.

### 7c. First test case

`tests/test_ledger.py`:

```python
def test_spend_recorded_with_attribution(stub_stream):
    # run one EXECUTE-tier relay call; provider reports 1000 in / 500 out on a $3/$15 model
    run_relay_call(task_ref="doc-123")
    row = latest_spend()
    assert row.tier == "EXECUTE" and row.task_ref == "doc-123"
    assert abs(row.usd - (1000*3 + 500*15) / 1_000_000) < 1e-9

def test_ratio_gates_budget(db):
    seed_spend(days=7, total=20.0); seed_revenue(days=7, total=200.0)
    assert ledger.ratio(owner) == 10.0
    assert budget_recommendation(owner) == "raise"    # emitted as `spend` approval item, never auto
```

---

## Section 8 — The Priority Arbitration Engine

### 8a. Design

One scoring function used by three consumers: approval-queue ordering (Section 4), handoff `priority_score` (Section 5), and the cmd-center hero ("what's the next block for"). It does not move calendar events — it recommends; time changes are `schedule_change` approval items (never auto, per Section 4).

**Configuration** — `data/settings.json` key `priority_config` (per-owner overridable):

```json
{
  "domains": {
    "dissertation": {"base": 9, "deadline": "2026-08-15", "revenue_linked": false},
    "jobs":         {"base": 8, "deadline": "2026-09-05", "revenue_linked": true},
    "consulting":   {"base": 6, "deadline": null,          "revenue_linked": true},
    "relocation":   {"base": 7, "deadline": "2026-09-05", "revenue_linked": false},
    "system":       {"base": 3, "deadline": null,          "revenue_linked": false}
  },
  "weights": {"base": 1.0, "deadline": 1.5, "revenue": 0.8, "staleness": 0.5, "human_blocked": 2.0},
  "starvation_days": 3
}
```

**Scoring function** (`src/orchestration/arbiter.py`):

```
score(item) =
    w.base     * domain.base
  + w.deadline * deadline_pressure          # 0 if no deadline; else min(10, 30 / days_remaining)
  + w.revenue  * revenue_signal             # 0 if not revenue_linked; else min(10, expected_usd / 100)
  + w.staleness* staleness                  # min(10, days_since_last_progress_on_domain)  ← from blackboard
  + w.human_blocked * (1 if item is the only thing blocking downstream agent work else 0)

Tiebreak: smaller estimated human effort first (batch the cheap decisions).
Starvation guard: any domain with zero blackboard progress events for `starvation_days`
gets +5 on its next item — dissertation can lose a battle, never the war.
```

Deadline pressure is why this starts correct for the current constraints: at 39 days out, dissertation scores `1.5 × min(10, 30/39) ≈ 1.2` deadline points on top of base 9 — and climbs every day. Relocation overtakes consulting automatically in late August without anyone editing a config.

### 8b. Implementation

- **New:** `src/orchestration/arbiter.py` (`score(item) -> float`, `rank(items)`, `starvation_bonus(domain)`); `priority_config` in `DEFAULT_SETTINGS`.
- **Modify:** `src/approvals.py` (score on create), `src/handoff_packet.py` (score on create), `services/home/cmd_center.py` (hero = top-ranked pending item across approvals + handoffs + jobs-attention, replacing the current hardcoded branch order).
- Staleness reads `blackboard_events` grouped by domain (domain inferred from `task_kind`/`task_ref`; jobs → `jobs`, skill runs carry their skill's category).

### 8c. First test case

`tests/test_arbiter.py`:

```python
def test_deadline_pressure_rises(frozen_time):
    cfg = default_priority_config()
    s39 = score(item(domain="dissertation"), today="2026-07-07", cfg=cfg)
    s10 = score(item(domain="dissertation"), today="2026-08-05", cfg=cfg)
    assert s10 > s39

def test_starvation_guard(db):
    seed_blackboard(domain="dissertation", last_progress=days_ago(4))  # > starvation_days
    ranked = rank([item(domain="consulting", expected_usd=200),
                   item(domain="dissertation")])
    assert ranked[0].domain == "dissertation"
```

---

## The 14-Day Build Plan

Dependencies flow downward. Each phase ends with its tests green (`pytest tests/test_<phase>*.py`) before the next starts. No phase touches more than 5 files without splitting into sub-agent-sized chunks.

| Days | Deliverable | Sections |
|---|---|---|
| 1 | Fix status/terminal_status bug + brief filter; migration script for memory JSON→SQLite (run, verify, don't delete JSON) | 0, 2 |
| 2–3 | Orchestration router + verifier tier settings; rewire handoff relay & task scheduler to tiers | 1 |
| 3–4 | Spend ledger (tables, price file, `llm_core` hook, `/api/ledger/summary`) — instrument early so the rest of the build is itself metered | 7 |
| 5–6 | Approvals (table, module, routes, decide-batch, brief Decisions section, cmd-center panel) | 4 |
| 7–8 | Close Engine (approval_pending flow, email poller classifier hook, consulting branch) | 3 |
| 9–10 | Blackboard + handoff packet v2 (all three builder copies + watcher script) + verified completion | 5 |
| 11 | Memory layers (loading rules, context-bundle endpoint, `memory_gc` builtin) | 2 |
| 12 | Arbiter + wire into approvals/handoffs/cmd-center hero | 8 |
| 13 | Skill machines: format support + rewrite the 4 skills, delete the duplicate | 6 |
| 14 | Integration pass: seed one real job lead end-to-end (email → auto-ingest → evaluate → tailor via relay → verify → approval → simulated approve → applying); revenue ratio in brief; full `pytest` run | all |

**Definition of done (system-level):** a job-lead email arriving at 09:00 produces, by the next 07:00 brief, exactly one approval line with a verified, tailored application package behind it — having consumed a logged number of dollars, at the correct model tiers, with every step visible on the blackboard, and zero human touches before the batch.

---

## Operability Clause (designing for obsolescence)

This spec is executable by a non-frontier model because:

1. **No design decisions remain.** Every schema is written out; every threshold has a number; every new module has a name and a home.
2. **Every section names the exact existing files to modify** and the existing patterns to copy (idempotent `ALTER TABLE` migrations, housekeeping-task seeding, route module structure, `tests/test_job_pipeline_phase*.py` test conventions).
3. **Each phase is independently verifiable** by its listed test case before proceeding — an implementing agent that runs the tests cannot silently drift.
4. **The system supervises its own construction:** the ledger (built day 3–4) meters the build; the verifier tier (day 2–3) checks handoff work from day 9 onward; failures file approval items instead of stalling.

Where an implementing agent finds this spec contradicts the code, the code's *data* wins (real column names, real statuses) and the spec's *intent* wins (one approval queue, tiers enforced in code, nothing surfaces unverified) — file a `pipeline_error`-category approval item describing the conflict rather than improvising.
