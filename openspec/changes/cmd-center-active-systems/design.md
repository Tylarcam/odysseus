## Context

V.A.U.L.T.'s backend (`services/home/cmd_center.py:build_cmd_center()`) is a pure aggregator: every request/poll re-derives all payload fields fresh from DB rows (Notes, Documents, ScheduledTask/TaskRun, JobRecord, calendar events) plus a MemPalace CLI shell-out. There is no background worker that mutates state on a schedule beyond the existing hourly `action_check_email_urgency` task. Migrations in this codebase are hand-rolled — `core/database.py` guards `ALTER TABLE ... ADD COLUMN` calls with a column-existence check (see `handoff_doc_id`/`handoff_relay_status` added to `notes` this way) — there is no Alembic. PROD's handoff fields are themselves just bolted-on `Note` columns, which is the existing precedent for "give an existing row a new cross-cutting concern" in this repo.

The MemPalace bridge (`services/mempalace/bridge.py`) shells out to the `mempalace` CLI (`status` subcommand only) and regex-parses wing/room/drawer counts. I verified directly: the installed `mempalace` CLI (v3.4.0) exposes `{init, mine, sweep, sync, search, compress, wake-up, split, hook, instructions, repair, repair-status, mcp, migrate, migrate-wings, status}` — **no `kg-query`/`traverse`/`graph-stats`/`find-tunnels` subcommand exists**, and `import mempalace` fails (`ModuleNotFoundError`) in this environment, so it isn't an importable library either. The rich graph tools (`mempalace_kg_query`, `mempalace_traverse`, etc.) are exposed only as MCP tools reachable by the Claude agent over the MCP stdio protocol — not something `services/mempalace/bridge.py` (a plain Python backend module, no MCP client) can call in-process today. This materially changes what's achievable for MYCELIA in this change — see Decision D5 and Open Questions.

## Goals / Non-Goals

**Goals:**
- Give directive-worthy objects a cheap, additive way to reference what spawned them, so tabs can render chains instead of isolated rows.
- Make "this has been sitting untouched too long" a first-class, computed-at-read-time signal that escalates urgency wherever the object is shown, not just in one panel.
- Fix the AGENCY undercount bug as a quick, isolated win that doesn't wait on the rest of the program.
- Leave tab-by-tab build sequencing open — the user will share top-3 goals separately to drive priority; this design fixes the *technical* dependency order (backbone before consumers) but not the *business* order tabs get built in.

**Non-Goals:**
- No backfill of historical lineage. `related_to` is recorded only for links created after this change ships; old jobs/handoffs/notes stay unlinked. Retroactive linking (e.g. fuzzy-matching old handoffs to old jobs) is a separate, much fuzzier problem and out of scope.
- No background worker/cron that periodically writes a persisted `stalled` flag. Staleness is computed fresh every time `build_cmd_center()` runs, exactly like every other field today.
- No attempt to wire the MCP-only MemPalace graph tools into the backend process in this change (see Decision D5) — that requires a capability MemPalace doesn't currently expose outside the MCP protocol.
- No new frontend visualization framework — lineage/stalled rendering extends the existing `cmdCenter.js` component patterns (badges, chips, popovers), not a new graph UI widget.
- No multi-tenant/permissions concerns — this is a single-operator HUD, same trust boundary as today.

## Decisions

**D1 — Lineage storage: a generic edge table, not per-model FK columns.**
`related_to` needs to point from any of {Note, JobRecord, TaskRun-adjacent task, handoff (itself a Note)} to any other of the same set. Bolting a `related_<kind>_id` column onto each model (the existing handoff-on-Note precedent) would require a combinatorial set of nullable FK columns across 3+ tables and doesn't generalize to "one note has two spawning parents." Instead: a small new table, e.g. `lineage_edges(id, source_kind, source_id, target_kind, target_id, relation, created_at)`, added via the same guarded-`ALTER`/`CREATE TABLE IF NOT EXISTS` pattern already used in `core/database.py`. `kind` is a short string enum (`note`, `job`, `handoff`, `task_run`); `id` is that row's existing primary key (already a string/UUID in every case per the audit). Writers: `job_pipeline/materialize.py` (job→handoff), `builtin_actions.action_check_email_urgency` (email uid→reminder note, using `account_id:uid` as a synthetic source id since email isn't a DB row), PROD's "+ new task" flow (note→task, though today task *is* a note — this becomes a self-referential "promoted from" edge once note-vs-task distinction exists per D4). Readers: `_build_priority_queue`, `build_globe_graph`, per-tab panel builders — all do a single batched lookup keyed by the ids already being rendered, not N+1 queries.
- *Alternative considered:* JSON column per model (`related_to_json` on Notes/JobRecord). Rejected because it still needs one column added per table and makes "find everything that points at X" (needed for MEM clustering and the globe graph) an unindexed scan across N tables instead of one indexed table.

**D2 — Stalled-item detection is a pure function computed at read time, not a persisted flag.**
Generalize `_is_stale_brief`/`_stale_missed_days` (`cmd_center.py:65-94`) into a per-kind SLA table (job needs-review > 3 days, handoff claimed-but-incomplete > N hours, task in-progress with no update > N days, directive note untouched — thresholds tunable, ship conservative defaults) evaluated fresh every `build_cmd_center()` call, same as every other derived field today. A background job that writes a `stalled=true` flag to the DB would itself need its own staleness guarantee (what if the job doesn't run?) — computing it live avoids that infinite regress and fits the codebase's existing "everything derived fresh" architecture.
- *Alternative considered:* scheduled task that flags + notifies. Not rejected outright — worth revisiting once the read-time version is live, since a scheduled pass could *also* push a proactive notification (not just wait for the operator to open the HUD). Left as a possible follow-on, not blocking this change.

**D3 — PROD task status moves onto the `notes` table, following the handoff-column precedent.**
Add `task_status` (`queued|in_progress|blocked|done`, nullable) and `task_status_at` (timestamp) columns to `notes` via the same guarded-`ALTER` pattern as `handoff_doc_id`. This makes "blocked" a real, cross-device, server-truth state for the first time. The client-side `localStorage` maps (`odysseus-cmd-prod-orbital-status-v1`, `-done-v1`) get a one-time migration-on-read: if a note has no `task_status` but the browser has a localStorage entry for it, POST it once to backfill, then stop reading localStorage for status going forward (still fine to keep as a UI hint layer for anything the backfill missed, e.g. cross-device stale state — but source of truth flips to the server field).

**D4 — AGENCY undercount fix ships independent of the rest of the program.**
`get_jobs_for_brief()` (`src/job_pipeline/brief.py`) takes `len()` of a `limit=5` query for `needs_review_count`/`ready_to_apply_count`. Fix: use `count_job_records(attention=...)`-style real counts (add if it doesn't exist in `src/job_pipeline/store.py`) separate from the capped `limit=5` list used for row display. This is a one-file, low-risk fix with no dependency on the lineage backbone — do it first, in its own commit/PR, regardless of how the rest of this change is sequenced.

**D5 — MYCELIA's MemPalace graph wiring is descoped to what's actually callable; true graph-tool wiring is an open question, not a commitment.**
Since the backend process cannot invoke `mempalace_kg_query`/`traverse`/`find_tunnels` (MCP-only, verified above), MYCELIA's realistic near-term improvement is: (a) replace the `swarm-`-prefix/title-substring convention with an explicit registry (real metadata on swarm tasks — this part is fully backend-owned and unblocked), and (b) for the MemPalace side specifically, either shell out to `mempalace search` for a real content signal (richer than `status`'s drawer counts, still short of true graph traversal) or leave the current CLI-status bridge in place until MemPalace ships a queryable interface reachable outside the MCP protocol (an HTTP mode, or a `kg-query`-equivalent CLI subcommand). Recommend not promising full graph-tool parity in this change's tasks.md; scope MYCELIA's spec to what's actually buildable now and flag the rest as a follow-on contingent on MemPalace's own roadmap.

**D6 — Sequencing across tabs is left to the user, but technical dependency order is fixed.**
Regardless of which tab the user prioritizes first (their top-3 goals, to be shared separately), the lineage backbone (D1) and stalled-item detector (D2) must exist before any tab's "system" behavior can be built on top of them — every per-tab capability in this change reads from those two. `tasks.md` phases the backbone + AGENCY fix first, then leaves per-tab phases as independently orderable.

## Risks / Trade-offs

- **[Risk] Lineage chains could get deep or cyclic in rendering (job→handoff→note→task→...)** → Mitigation: cap rendered chain depth to 1 hop in hero/queue/stage-card surfaces (show immediate parent only); full chain walk available only in an explicit click-through/detail view, and the edge writer path is a DAG by construction (nothing here creates a cycle today) but render code should not assume that forever.
- **[Risk] SLA thresholds for "stalled" are guesses until lived-in** → Mitigation: ship conservative defaults, make thresholds a config dict in one place (not scattered constants), expect a tuning pass after a week of real use.
- **[Risk] MemPalace true graph-tool wiring may simply not be achievable in-process** → Mitigation: D5 descopes this honestly rather than shipping a task that can't be completed; MYCELIA's spec should describe the registry piece as committed and the graph-tool piece as contingent/exploratory.
- **[Risk] New `lineage_edges` table + two new `notes` columns is schema surface added to a system with no formal migration framework** → Mitigation: follow the exact guarded-`ALTER`/existence-check pattern already proven in `core/database.py`; both additions are purely additive/nullable, so no backfill or downtime is required and old rows simply have no lineage/status until touched again.
- **[Trade-off] Computing stalled-ness fresh every request is simpler than persisting it but repeats the same date-math on every poll** → acceptable: the existing `_compute_payload_hash` short-circuit (from the sibling `vault-cmd-center-focus-orchestration` change) already avoids full rebuilds on unchanged polls, so this cost is paid once per actual change, not once per 30s tick.

## Migration Plan

1. Add `lineage_edges` table (new, empty at deploy — no backfill).
2. Add `notes.task_status` / `notes.task_status_at` columns (nullable, additive).
3. Deploy backend read/write plumbing behind the new fields; old payload consumers ignore fields they don't recognize (additive JSON keys), so frontend can roll out slightly behind backend without breaking.
4. Frontend: one-time localStorage→server backfill read for PROD status (D3), then stop trusting localStorage as source of truth.
5. Rollback: both schema additions are inert if unused — reverting backend code is sufficient; no destructive rollback step needed for the DB changes themselves.

## Open Questions

- Does MemPalace plan to expose `kg_query`/`traverse`/`graph_stats`/`find_tunnels` (or equivalent) via a queryable CLI subcommand or local HTTP endpoint, as opposed to MCP-only? This blocks true graph-tool wiring for MYCELIA (D5) until resolved upstream.
- What are the right default SLA thresholds per kind (job needs-review days, handoff claimed-but-stuck hours, task in-progress days)? Proposed as conservative starting guesses in D2; needs a short real-world tuning pass.
- Which tab ships first? Left to the user's top-3 goals (not yet shared) — this design and `tasks.md` phase the shared backbone first and leave per-tab work independently orderable after that.

## Deferred (Phase 8 decision)

**MemPalace MCP graph tools are deferred — not partially implemented.**

At Phase 8 implementation time (2026-07-31), the installed MemPalace CLI (v3.4.0) still exposes no `kg-query` / `traverse` / `graph-stats` / `find-tunnels` subcommand, and `import mempalace` remains unavailable in the Odysseus backend process. The rich graph tools remain MCP-stdio-only.

What shipped instead for MYCELIA's MemPalace signal:
- Explicit swarm-task registry (`services/home/swarm_registry.py`) — committed
- `mempalace search` content-hit bridge (preferred), with `status` wing/room inventory as fallback — committed in `services/mempalace/bridge.py`

What is explicitly **not** claimed:
- `kg_query` / `traverse` / `graph_stats` / `find_tunnels` parity in MYCELIA / `mycelia_stats`
- Any in-process MCP client shim that would fake graph traversal

Revisit when MemPalace ships a queryable non-MCP interface (CLI subcommand or local HTTP). Until then, do not partially wire MCP graph tools into the backend.
