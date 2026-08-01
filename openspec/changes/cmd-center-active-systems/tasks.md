## 0. Quick, independent fix (no dependency on anything below)

- [x] 0.1 Add a real count query (e.g. `count_job_records(attention=...)`) in `src/job_pipeline/store.py`, separate from the capped `limit=5` list query
- [x] 0.2 Update `get_jobs_for_brief()` (`src/job_pipeline/brief.py`) to use the real count for `needs_review_count`/`ready_to_apply_count` instead of `len()` of the capped list
- [x] 0.3 Add/adjust a `tests/test_home_dashboard.py` case with >5 jobs in a bucket asserting the count is uncapped

## 1. Lineage backbone (`cmd-center-lineage`) — prerequisite for every tab section below

- [x] 1.1 Add `lineage_edges` table via the guarded `CREATE TABLE IF NOT EXISTS` pattern already used in `core/database.py` (`source_kind`, `source_id`, `target_kind`, `target_id`, `relation`, `created_at`)
- [x] 1.2 Add a small write helper (e.g. `record_lineage_edge(...)`) and a batched read helper (e.g. `lineage_for(kind_id_pairs)`) in `core/database.py` or a new `core/lineage.py`
- [x] 1.3 Wire the write helper into `job_pipeline`'s materialize path (job→handoff, `relation="materialized"`)
- [x] 1.4 Wire the write helper into `action_check_email_urgency` (`src/builtin_actions.py`) where it creates a reminder note (`relation="reminded"`, synthetic source id `account_id:uid`)
- [x] 1.5 Wire the write helper into the PROD "+ new task" flow where a task note references a source note (`relation="promoted"`)
- [x] 1.6 Ensure all writes are non-blocking/fail-soft per the spec (log on failure, never raise into the caller's primary action)
- [x] 1.7 Add `tests/test_home_dashboard.py` (or a new `tests/test_lineage.py`) coverage: edge write on each of the three flows above, batched read returns correct results, failed write doesn't break the primary action

## 2. Stalled-item detector (`cmd-center-stalled-item-detection`) — prerequisite for every tab section below

- [x] 2.1 Define one config location for per-kind SLA thresholds (job needs-review days, handoff claimed-stuck hours, task in-progress days), generalizing `_is_stale_brief`/`_stale_missed_days` (`cmd_center.py:65-94`)
- [x] 2.2 Implement a pure `compute_stalled(kind, obj, now)` function returning `None` or `{since, reason}`, computed at read time only (no persisted flag)
- [x] 2.3 Wire `compute_stalled` into `_build_priority_queue()` so stalled objects get an urgency boost
- [x] 2.4 Add tests: threshold boundary cases per kind, confirm no persisted state (recompute reflects live status changes across two calls)

## 3. CORE (`cmd-center-core-system`)

- [x] 3.1 Attach `related_to` (1-hop) to `priority_queue` items using the batched lineage read
- [x] 3.2 Add cross-object edges to `build_globe_graph()` (`services/home/kg_graph.py`) wherever a lineage edge connects two rendered nodes
- [x] 3.3 Ensure stalled-chain items surface at escalated urgency per the spec scenario (stalled source escalates independent of a healthy-looking terminal item)
- [x] 3.4 Update/extend `tests/test_home_dashboard.py` for chain rendering and globe edge cases

## 4. PROD (`cmd-center-prod-system`)

- [x] 4.1 Add `notes.task_status` / `notes.task_status_at` columns via guarded `ALTER TABLE` in `core/database.py`
- [x] 4.2 Add a backend endpoint/path to write `task_status` (reuse or extend the existing notes update path)
- [x] 4.3 Update `static/js/cmdCenter.js` PROD board (`_bucketProdQueue`, `_normalizeProdOrbitalItem`, `_resolveOrbitalStatus`) to read/write server `task_status` instead of `localStorage`
- [x] 4.4 Add the one-time localStorage→server backfill-on-read described in design.md D3
- [x] 4.5 Wire stalled in-progress tasks into `priority_queue` (depends on Section 2)
- [x] 4.6 Show `related_to` on PROD task cards (depends on Section 1)
- [x] 4.7 Tests: status persists across a simulated "different device" read; blocked round-trips; stalled in-progress task appears in priority_queue

## 5. COMMS (`cmd-center-comms-system`)

- [x] 5.1 Confirm lineage write from Section 1.4 covers the reminder-note case end to end — evidence: `create_urgent_email_reminder_note` writes `email→note` edges with `relation="reminded"` + synthetic `account_id:uid`; `action_check_email_urgency` calls it after successful reminder delivery (`src/builtin_actions.py`); covered by `test_urgent_email_reminder_note_records_reminded_edges` (related_to shape `{kind:"email", id}` matches comms-system scenario)
- [x] 5.2 Add closed-loop conversion-rate computation to `comms_focus` (count `relation="reminded"` edges in the rolling window)
- [x] 5.3 Add unread-urgent->48h check into the stalled-item detector config (Section 2.1) and wire into `priority_queue`
- [x] 5.4 Tests: conversion count over a window, 48h escalation boundary

## 6. AGENCY (`cmd-center-agency-system`)

- [x] 6.1 Expose pipeline funnel stage counts (ingested/evaluated/ready/applied) from `job_pipeline` state into AGENCY's payload
- [x] 6.2 Attach `related_to` (job→handoff) on job rows using the lineage read from Section 1
- [x] 6.3 Wire stalled-in-review jobs (Section 2) into `priority_queue`
- [x] 6.4 Tests: funnel counts match underlying job_pipeline state; lineage present when a handoff exists; stalled-review escalation

## 7. RELAY (`cmd-center-relay-system`)

- [x] 7.1 Attach `related_to` (job/note origin) on handoff rows using the lineage read from Section 1
- [x] 7.2 Distinguish `claimed_stuck` from `needs_attention` in `relay_board` using the stalled-item detector (Section 2)
- [x] 7.3 Add an outcome/close-rate computation to `relay_stats` (completed vs. failed vs. open over a rolling window)
- [x] 7.4 Tests: stuck-vs-attention bucket separation, close-rate math

## 8. MYCELIA (`cmd-center-mycelia-system`)

- [x] 8.1 Design and add an explicit swarm-task registry (metadata, not ID-prefix convention) replacing `swarm-` prefix checks and hardcoded title-substring matching (`cmd_center.py:1043-1052`, `_find_doc`, `mycelia_commands`)
- [x] 8.2 Migrate existing swarm tasks/docs into the new registry
- [x] 8.3 Investigate feasibility of a richer MemPalace content signal callable from the backend (e.g. `mempalace search`) to replace the CLI-`status`-only bridge; implement if feasible within this change
- [x] 8.4 If full graph-tool wiring (`kg_query`/`traverse`) is not feasible in-process (per design.md Open Questions), explicitly document that as deferred rather than partially implementing it
- [x] 8.5 Tests: registry-based swarm detection (including the "coincidental name, not registered" negative case)

## 9. Documentation follow-up (tracked, not blocking)

- [x] 9.1 Update `docs/vault-cmd-center-component-atlas.md` to describe lineage/stalled fields once the above ships (flagged in design.md as a known follow-up, do after implementation stabilizes rather than mid-flight)
