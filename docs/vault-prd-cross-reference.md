# V.A.U.L.T. Cross-Reference — Insights vs. Completion PRD

> Reconciles `docs/vault-ceo-transcript-insights.md` (feature backlog, Tiers A–F) with `docs/vault-cmd-center-prd.md` (engineering completion, Phases 1–4). One document per Tier, with: PRD gaps each insight touches, whether it extends an existing key or needs a new one, phase alignment, and acceptance criteria.
>
> **Status:** synthesis only — no code. For implementation, use the per-phase agent prompts in §6.

---

## 1. Source documents

| Doc | Role | Phase numbering |
|-----|------|-----------------|
| `docs/vault-cmd-center-prd.md` | Engineering completion — what's left in the build | Phases **1–4** (1–2 shipped; 3 = P0/P1; 4 = P2–P4) |
| `docs/vault-ceo-transcript-insights.md` | Feature backlog from CEO-transcript research | Phases **5–8** (invented here, does **not** match PRD numbering) |
| `docs/odysseus-data-dictionary.md` §5 | Authoritative payload shape for `/api/home/cmd-center` | n/a |

### Numbering mismatch — important

The insights doc originally introduced **Phases 5–8** for its priority implementation order. The PRD has no Phases 5–8 — its next work is **Phase 3** (P0/P1 gaps) and **Phase 4** (P2–P4 polish). Two readings:

1. **The insights doc means "after PRD is done"** — i.e., a fresh backlog on top of a fully-shipped PRD. Most likely intent based on the doc body.
2. **The insights doc is renumbering the PRD** — i.e., Tier A items are really Phase 3.5 work. Less likely given the doc's own agent prompt footer.

**Resolved 2026-07-04:** the insights doc's phases have been renamed to **Waves 1–4** to remove the ambiguity. The Waves are post-PRD work, not the next thing to pick up. PRD Phase 3 and Phase 4 remain authoritative. The cross-ref and the insights doc now agree: finish PRD-3 first (G-01, G-05, G-11 are P0 blockers), then PRD-4, then Wave 1.

---

## 2. Current payload (verified against `services/home/cmd_center.py`)

Keys already produced by `build_cmd_center()` (lines 634–664):

- `branch_health[]` — `{id, label, state, count, summary, action}` (per G-13 missing Intel/Voice)
- `priority_queue[]` — `{id, kind, title, subtitle, branch, urgency, action, target_id, ts}` (max 12, sorted by `-urgency, -ts`)
- `hero` — first non-zero among: handoffs → jobs → directives → notes
- `suggested_commands[]`
- `jobs_detail` — `{ready_to_apply[], needs_review[]}` from `services/jobs/brief.py`
- `plan_note_id`
- `audio` — static, voice stats not wired
- `counts` — includes `handoffs_in_progress`
- `wire[]` — `{ts, text, action, target_id, branch}`
- `synced_at`

**Confirmed absent** (no matches in `cmd_center.py` or `cmdCenter.js`):

- `quick_read` / `human_item` — no concept exists
- `stale_days`, `fit_score` — no concept exists
- NEEDLE / SPIN / IN_FLIGHT tags — none
- Compute mode (`PRIVATE` / `CONNECTED` / `CLOUD`) — no concept exists
- Wire filter chips — PRD G-14 is still open

This means **every Tier A insight introduces a new payload key** (or, in T-A3's case, a new field on existing job rows). None can be implemented as pure frontend work.

---

## 3. Per-Tier cross-reference

### Tier A — Highest needle

| Insight | Touches PRD gap(s) | Payload change | Phase alignment | Notes |
|---------|--------------------|----------------|-----------------|-------|
| **T-A1** CEO Quick Read strip | G-03 (AM card), G-21 (hero expandable) | **New** `quick_read: {do_today, delegated, calendar, email, blocked[]}` at top level | Wave 1, after PRD Phases 3+4 | Replaces "long hero prose" per insights doc. Render in `cmdCenter.js` under topbar — 5 bullets max, each clickable. |
| **T-A2** Single HUMAN slot | G-21 (hero expandable), G-17 (morning ritual) | **New** `human_item: {id, kind, title, branch, action, target_id, score}` | Wave 1 | One row picked from `priority_queue` by scoring rule. Insights doc gives the rule (revenue/deadline > handoff > job apply). **Needs explicit scoring function** — not derivable from current `urgency` alone. |
| **T-A3** Stale heat on jobs | **G-01** (job panel read-only), G-15 (real vitals) | **Extends** `priority_queue[]` job rows: add `stale_days: int`, `fit_score: int (1–5)`. Sort boost: stale_days × fit_score. | Wave 1; **data dependency blocks** | Job store must expose `fit_score` and a `last_touched`/`updated_at` field. `services/jobs/brief.py` doesn't compute either today — this is a backend prerequisite, not just a builder change. |
| **T-A4** One-click CEO follow-up | **G-01**, G-04 (plan today), T-B2 (playbook) | **New** action `follow_up_email` + email-draft API surface | Wave 2 | Insights doc wants follow-up draft to open in **email library**, not generic Notes. Requires either a new endpoint or reuse of `routes/email_routes.py` draft flow. Verify both paths exist before committing. |
| **T-A5** NEEDLE vs SPIN tag | G-15 (real deltas), G-14 (wire filters) | **Extends** `priority_queue[]` rows: add `tag: NEEDLE\|SPIN\|INTEL\|IN_FLIGHT` | Wave 1 | Tagging rule lives in insights doc but is not yet codified. Need a single source of truth — recommend a helper `_classify(item) -> tag` in `cmd_center.py` with tests. |

### Tier B — Intel & learning loop

| Insight | Touches PRD gap(s) | Payload change | Phase alignment | Notes |
|---------|--------------------|----------------|-----------------|-------|
| **T-B1** Intel Ingest (video URL) | (new surface) | **New** route + `branch_health.intel` count + wire entries | Wave 2 | `data/skills/general/youtube-ceo-brief/SKILL.md` already implements the skill. Vault integration = a new `cmd` action `intel_ingest` that opens a URL input and dispatches to the skill. |
| **T-B2** Playbook panel | G-21 (hero expandable), G-22 (recent commands) | **New** `latest_brief: {id, title, playbook[], edges, wedges, edges_wedges}` | Wave 2 | Doc linked: playbook table format. Panel must read from most recent CEO-brief note. |
| **T-B3** Edges / Wedges chip | G-21 | (uses `latest_brief.edges_wedges`) | Wave 4 | Read-only render; cheap once T-B2 ships. |
| **T-B4** PROVEN vs CLAIMED | G-14 (wire filters) | **Extends** `wire[]` rows: optional `maturity: PROVEN\|CLAIMED` | Wave 4 | Only set for items originating from CEO brief pipeline; default omit. |

### Tier C — Agent orchestration

| Insight | Touches PRD gap(s) | Payload change | Phase alignment | Notes |
|---------|--------------------|----------------|-----------------|-------|
| **T-C1** IN_FLIGHT lane | G-15 (vitals), G-18 (directive actions) | **Extends** `priority_queue` with `tag: IN_FLIGHT` (reuses T-A5) | Wave 3 | Derived from `handoffs.in_progress` + running scheduled tasks already in payload. **Cheap to add** — does not require new data, only a new tag and a sub-panel. |
| **T-C2** Delegate from queue | G-18 (directive actions) | **New** actions `delegate_cursor`, `delegate_claude` | Wave 3 | Insights doc says "creates handoff packet w/ real doc id + pickup line." This requires the handoff system to accept a `priority_queue` row as input, plus a pickup line template. Spec out the pickup line format before implementation — Ras prompt says anti-pattern = vague. |
| **T-C3** Agent heartbeat strip | **G-11** (live updates) | **New** `heartbeats: [{name, last_run_at, last_status, next_run_at}]` from `src/task_scheduler.py` | Wave 3 | Insights doc says this can poll before full SSE. PRD G-11 still has no SSE. **C-3 is a stepping stone** — the strip can refresh on a short interval, then the rest of G-11 catches up. |
| **T-C4** Ranked review queue | (new surface) | **Defer** per insights doc (no git API) | n/a | Placeholder: rank **documents** or **handoffs** by age + type. Confirm which signal drives ranking before building. |
| **T-C5** HTML plan review links | G-19 (relay watcher UX) | (frontend only) | Wave 3 | Handoff cards already have a `target_id`; just need a `preview_url` field on handoffs. Verify handoffs have one. |

### Tier D — Privacy & compute modes

| Insight | Touches PRD gap(s) | Payload change | Phase alignment | Notes |
|---------|--------------------|----------------|-----------------|-------|
| **T-D1** Compute mode indicator | (new surface) | **New** `compute_mode: PRIVATE\|CONNECTED\|CLOUD` at top level | Wave 3 | Derived from active chat model + voice gateway. Source of truth is `src/llm_core.py` + `/api/voice/stats` (G-05 in flight). |
| **T-D2** Sensitive brief route | T-B1 | (frontend toggle + query param) | Wave 3 | Olivia's solution brief describes the pipeline. Toggle must suppress the intel item from `wire[]` if the route forces local-only. **Watch for data leak** in the unfiltered path. |
| **T-D3** Delegation class on actions | T-A4, T-C2 | **Extends** `priority_queue[]` rows + `suggested_commands[]` with `delegation: Local\|Staff\|Cursor\|Claude\|External` | Wave 3 | Reuses executive brief template's class taxonomy. Tag at creation, not at render. |

### Tier E — Morning ritual

| Insight | Touches PRD gap(s) | Payload change | Phase alignment | Notes |
|---------|--------------------|----------------|-----------------|-------|
| **T-E1** Start Day flow | **G-17** (morning ritual) | (orchestration only; uses existing keys) | Wave 2, **after G-17** | T-E1 explicitly merges Ras phases 1→5 into the vault's morning mode. Effectively **supersedes** G-17's narrower spec. Decide: replace G-17 with T-E1, or layer T-E1 on top. Insights doc implies the former. |
| **T-E2** Post-call brief hook | (new surface) | (calendar integration + ingestion) | Wave 4 | Requires calendar event "screen" label. Verify CalDAV sync supports labels (`src/caldav_sync.py`). |
| **T-E3** Expansion radar | (new surface) | **New** `expansion_accounts: [{name, signal, last_touch}]` from CRM notes | Wave 4 | "Agency card when no jobs" is the trigger condition. Confirm jobs-brief is the source of truth for "no jobs." |

### Tier F — Work pattern audit

| Insight | Touches PRD gap(s) | Payload change | Phase alignment | Notes |
|---------|--------------------|----------------|-----------------|-------|
| **T-F1** Needle : busywork ratio | G-15 (real vitals) | **New** `pattern: {needle_pct, spin_pct, window_days}` at top level | Wave 4 | Reuses T-A5's tag. Computed by aggregating `tag` across all `priority_queue` items over a window. Cheap once T-A5 ships. |
| **T-F2** Repeated question → skill | (new surface) | **New** daily job: aggregate `wire[]` text, surface ≥N repeats | Wave 4 | Background job, not on hot path. Add to `src/task_scheduler.py`. |
| **T-F3** Operating rhythm table | G-17 (morning ritual) | (settings surface) | Wave 4 | "One-click enable task" reuses the task scheduler API. Confirm scheduler supports one-click enable from a non-admin surface. |

---

## 4. Conflicts and gaps to resolve before coding

1. **Phase numbering — resolved.** The insights doc's "Phase 5–8" was post-PRD, not a rename of PRD Phase 3, but the collision was ambiguous. Fixed by renaming insights phases to **Waves 1–4** in `docs/vault-ceo-transcript-insights.md`. Both docs now agree.
2. **T-A3 data dependency.** `stale_days` and `fit_score` are not in the job store. Insights doc treats this as a builder change; it's actually a `services/jobs/brief.py` change. **Add a prerequisite task**: "Compute + persist `fit_score` per job and `stale_days = today - updated_at`."
3. **G-17 vs T-E1.** PRD G-17 is a narrow "first open of day → highlight morning card." T-E1 absorbs this into a full Ras-phases 1→5 flow. **Decide which one ships.** Recommendation: ship G-17 first (smaller, no scoring change), then T-E1 as a v2 expansion.
4. **G-11 vs T-C3.** PRD G-11 wants SSE for live updates. Insights T-C3 ships a polling heartbeat strip *first* and says SSE can come later. **Pragmatic:** ship T-C3 (cheap) under the G-11 acceptance criterion; revisit SSE when G-11 itself is worked.
5. **T-A4 destination.** Insights doc says email library, but `routes/email_routes.py` draft flow may not support the evidence-linked structure. **Verify** that `routes/email_routes.py` exposes a "create draft with body + linked docs" action, or that the builder can wire to a simpler `/api/email/draft` route. If not, T-A4 expands to a new route — re-scope.

---

## 5. Recommended execution sequence

This is what a real implementer should do, given both docs:

1. **Finish PRD Phase 3** — P0 blockers (G-01 job actions, G-05 voice SLO, G-11 live updates). These are unblocking several Tier A items.
2. **PRD Phase 4** — G-17 morning ritual, G-14 wire filter chips (these set up the surfaces insights-doc needs).
3. **Prerequisite for T-A3** — add `fit_score` + `stale_days` to job brief (no UI yet).
4. **Wave 1 (Tier A)** — T-A1, T-A2, T-A3, T-A5. Done when the 45-second scan test passes.
5. **Wave 2 (Tier B+A4+E1)** — T-B1, T-B2, T-A4, T-E1.
6. **Wave 3 (Tier C+D)** — T-C1, T-C2, T-C3, T-D1, T-C5, T-D3. T-D2 if the local-model route is already shipped in T-B1.
7. **Wave 4 (Tier B remnants+E2+F)** — T-B3, T-B4, T-E2, T-E3, T-F1, T-F2, T-F3.

---

## 6. Ready-to-run agent prompts (next 3 phases)

### Phase PRD-3 (finish first — unblocks Tier A)

```
You are finishing V.A.U.L.T. Phase 3 in repo odysseus. Read
docs/vault-cmd-center-prd.md and docs/odysseus-data-dictionary.md §5.

Work in 5-file chunks. Per chunk: code, run pytest tests/test_home_dashboard.py,
read back the file to confirm.

Chunk 1 (G-01, G-04): Make the job attention panel rows clickable.
  - services/home/cmd_center.py: jobs_detail rows gain `action` and `target_id`.
  - static/js/cmdCenterJobs.js: row click → action handler.
  - routes/jobs_routes.py: confirm `/api/jobs/<id>` GET exists; add POST `/api/jobs/<id>/mark-applied` if missing.
  - tests/test_home_dashboard.py: assert job row has action.

Chunk 2 (G-05): Wire voice stats.
  - routes/home_routes.py: fetch /api/voice/stats SLO, pass to build_cmd_center(voice=...).
  - services/home/cmd_center.py: branch_health.voice reflects degraded state.
  - static/js/cmdCenter.js: Audio I/O chip shows "Degraded" or "Standby" + p95.

Chunk 3 (G-11, T-C3 prep): Polling heartbeat.
  - static/js/cmdCenter.js: poll /api/home/cmd-center every 30s while open.
  - Replace wire + 3D pulse without full repaint (delta update).
  - Do NOT add SSE yet — that's a separate chunk.

After each chunk: pytest, manual 45-second scan test.
```

### Phase PRD-4 (after PRD-3, before Wave 1)

```
Continue V.A.U.L.T. Phase 4 in repo odysseus. Same 5-file rule.

Chunk 1 (G-17, narrow): Morning ritual — first open of day.
  - frontend: localStorage day key; first open → highlight Morning card.
  - services/home/cmd_center.py: surface `is_first_open_today: bool`.

Chunk 2 (G-14): Wire filter chips.
  - static/js/cmdCenter.js: chips All · Relay · Agency · Prod · Chat.
  - Filter wire[] in place; no backend change.

Chunk 3 (G-31): Update data dictionary §5.
  - docs/odysseus-data-dictionary.md: add new keys from PRD API contract.
```

### Wave 1 (after PRD-3 + PRD-4 land)

```
Read docs/vault-ceo-transcript-insights.md (Tier A), docs/vault-prd-cross-reference.md §3, and docs/odysseus-data-dictionary.md §5.

Implement T-A1, T-A2, T-A3, T-A5 in 5-file chunks. The cross-ref §4 lists
prerequisites — confirm the job store exposes fit_score and updated_at before
T-A3. If not, do that first as Chunk 0.

Chunk 0 (T-A3 prerequisite): Add fit_score + stale_days to job rows.
  - services/jobs/brief.py: compute fit_score (1-5) and stale_days.
  - services/home/cmd_center.py: pass through to jobs_detail + priority_queue job rows.
  - tests/test_home_dashboard.py: assert job row has both fields.

Chunk 1 (T-A1, T-A2): Backend scoring.
  - services/home/cmd_center.py: add quick_read{} and human_item{}.
  - Scoring for human_item: per insights doc rule (revenue/deadline > handoff > job apply).
  - Tests for scoring determinism.

Chunk 2 (T-A1 frontend): Render CEO Quick Read strip.
  - static/js/cmdCenter.js: 5 bullets, clickable.
  - Style: under topbar, one line each.

Chunk 3 (T-A2, T-A5 frontend): HUMAN row + NEEDLE/SPIN badges.
  - static/js/cmdCenter.js: priority queue rows get tag badge.
  - The human_item row renders distinctly.
  - Filter toggle: NEEDLE / SPIN / IN_FLIGHT / All.

Acceptance: 45-second manual scan test + pytest.
```

---

## 7. Open questions for the user

These are decisions only you can make; I won't infer them:

1. **Rename insights phases** to avoid collision with PRD numbering? (recommended)
2. **Replace G-17 with T-E1**, or layer T-E1 on top? (recommend: layer, ship G-17 first)
3. **T-A4 follow-up destination** — does `routes/email_routes.py` already support the evidence-linked draft, or do we add a new route?
4. **T-C3 polling cadence** — 30s? 60s? Pick one and stick to it; don't ship a "smart" interval.

---

## 8. Out of scope (carried from both docs)

- Token-maxxing / subscription arbitrage
- Full git PR judge workflows
- Hermes desktop app / Ollama install wizard
- CPG-specific CRM
- COMMUNITY / SALES / FINANCE branches
- Publishing pipeline / carousels

---

*Drafted 2026-07-04 from cross-read of `docs/vault-ceo-transcript-insights.md`, `docs/vault-cmd-center-prd.md`, `docs/odysseus-data-dictionary.md` §5, and a focused read of `services/home/cmd_center.py` + `static/js/cmdCenter.js`.*
