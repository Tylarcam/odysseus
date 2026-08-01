# V.A.U.L.T. Command Center — Component Atlas

> Every visible HUD region: provenance, goal, function, and rationale.
> Mirror of `CMD_COMPONENT_ATLAS` in [`static/js/cmdCenter.js`](../static/js/cmdCenter.js).
> Display toggles: gear icon in vault top bar → `localStorage` key `odysseus-cmd-center-visibility`.

---

## Data flow

```
Notes · Documents · Tasks · Handoffs · Jobs · Sessions · Calendar · TaskRuns · Voice · MemPalace
  → services/home/cmd_center.py:build_cmd_center()
  → GET /api/home/cmd-center
  → static/js/cmdCenter.js (render + actions)
```

**Live poll (default 30s, `cmdCenterLive.js`):** requests `include_globe=0` and the
last-seen `payload_hash` as `since_hash`. An unchanged poll gets back only
`{unchanged, synced_at, payload_hash}` — no DB-query re-render, no MemPalace
fetch. The initial open fetch always requests the full payload including
`globe_graph`; the frontend keeps rendering that last-known globe graph on
every poll after, since polls never re-fetch it.

---

## Toggleable components

| ID | UI region | Payload key(s) | Provenance | Goal | Function (click) | Rationale |
|----|-----------|----------------|------------|------|------------------|-----------|
| `status_pills` | Top bar + mobile HUD strip | `status`, `branch_health` | `_build_branch_health()` — notes, docs, tasks, handoffs, jobs, voice, swarm counts | Instant branch health | Pill → open that branch surface (`notes`, `tasks`, `agent_bin`, etc.) | Answer “what’s online vs on fire” in one glance |
| `vitals` | Left rail — System Vitals | `vitals[]` | Counts: notes (+pinned), documents, active scheduled tasks, agent-bin attention | Capacity snapshot | Row → `notes` / `library` / `tasks` / `agent_bin` | Honest counters; no fake sparklines |
| `priority_queue` | Left rail — Priority Queue | `priority_queue`, `directives` | `_build_priority_queue()` — urgency: handoffs (100) → jobs review (95) → ready (90) → due/pinned notes → active tasks; each item may carry `related_to` (1-hop) and `stalled` (read-time SLA); stalled items / stalled neighbors get an urgency boost | What needs you next | Row → `open_note`, `jobs`, or `agent_bin` | Single ranked work list for the day |
| `swarm_activity` | Left rail — Swarm Activity | `agent_activity[]` | Recent `task_runs`, registered swarm tasks first (`services/home/swarm_registry.py`), last 10 | See agents working | Row → `open_task` | Makes Mycelia visible without opening Tasks |
| `documents` | Left rail — Documents | `documents[]` | 8 newest non-archived documents by `updated_at` | Recent intel / drafts | Row → `open_doc` | Fast path into library artifacts |
| `globe_scene` | Center — Three.js mount | `globe_graph`, `branch_health` | `build_globe_graph()` — branch nodes + MemPalace content hits (`mempalace search`, preferred) with `status` wing/room fallback; cross-object edges from `lineage_edges` when both ends are rendered. MCP graph tools (`kg_query` / `traverse` / etc.) are **not** wired — deferred | Spatial system map | Node hover/click → branch action | Situation-room centerpiece |
| `stage_cards` | Center — float cards | `stage_cards[]` | CEO brief, morning/jobs, relay, plan today, vault sync, up-next from agenda | Ritual shortcuts | Card → `ceo_brief`, `jobs`, `agent_bin`, `open_note`, `refresh`, `calendar` | One-tap morning/ops moves |
| `hero` | Center — primary overlay | `hero` | `_build_hero()` — relay → agency jobs → directives → notes | Primary directive | Overlay + CTA → top-ranked action | “Within 5s know what’s on fire” |
| `command_deck` | Right rail — Command Deck | `commands[]`, `suggested_commands[]` | Fixed deck + Mycelia group (registry-backed swarm commands) + hero-branch suggestions | Do something now | Button → `_runAction` | Explicit operator controls |
| `audio_io` | Right rail — Audio I/O | `audio` | Voice stats / standby from builder + live voice UI events | Voice delegate without leaving vault | Click, or hold `Space` 3s anywhere in the vault → activate voice agent mode | Hands-free operator loop |
| `ai_wire` | Right rail — AI Wire | `wire[]` | Recent notes, docs, handoffs, jobs, sessions (newest first, max 16) | Live activity ticker | Row → open source item | Traceability — “what just happened” |
| `notes_rail` | MEM left — Notes | `notes_preview[]` | Newest non-archived notes (title, preview, pinned, tags) | Browse memory without leaving vault | Card → `open_note`; Open Notes → notes panel | Orbital MEM parity |
| `task_board` | PROD left — Tasks | `priority_queue` / `directives` (prod) | Prod items as orbital TaskCards; server `notes.task_status` / `task_status_at` (`queued` \| `in_progress` \| `blocked` \| `done`) is source of truth (one-time localStorage→server backfill on read); cards show `related_to` chips; stalled in-progress tasks escalate into the queue | Act on prod work | Card → note/task; START/DONE/REOPEN cycles `task_status` via notes update API | Orbital PROD parity |
| `mem_focus` | MEM right — Selected | counts from `notes_preview` | Brief + foundation shortcuts | Memory ritual | COMPILE BRIEF → `ceo_brief` | Orbital MEM right rail |
| `directive` | PROD right — Directive | `hero` + prod queue counts | Branch focus blurb | Know PROD intent | Plan Today / hero CTA | Orbital PROD right rail |
| `agency_board` | AGENCY left — Jobs & Agents | `jobs_detail`, `agent_activity` | Ready/review job rows (each with optional job→handoff `related_to`) + non-swarm runs; pipeline `funnel` counts live on `jobs_detail` | Act on job pipeline | Row / Open Jobs → `jobs` | Orbital AGENCY parity |
| `agency_focus` | AGENCY right — AM Report | `jobs_detail`, Agency commands | Headline + ready/review counts; uncapped `needs_review_count` / `ready_to_apply_count` (not `len` of the capped list) | Morning job ritual | Review Jobs + AM Report deck | Orbital AGENCY right rail |
| `relay_board` | RELAY left — Handoff Queue | `relay_board`, `branch_health` | Dedicated buckets: `needs_attention` · `claimed_stuck` (stalled claimed handoffs) · `in_progress`; rows carry origin-only `related_to` (`job` / `note` / `email`) | Triage handoffs | Row → `agent_bin` / Open Agent Bin | Orbital RELAY parity |
| `relay_stats` | RELAY right — Relay Stats | `relay_stats`, `counts`, `branch_health` (relay) | Waiting / stuck / in-flight plus rolling-window `issued` · `completed` · `failed` · `open` · `close_rate` | Relay health snapshot | Agent Bin · Install Relay | Orbital RELAY right rail |
| `comms_inbox` | COMMS left — Inbox | `comms_preview[]`, `branch_health` (comms) | Live INBOX rows (+ urgency overlay when scanned); unread-urgent past SLA escalates into `priority_queue` as stalled email | Triage unread mail | Row → `email` | Orbital COMMS parity (G-06) |
| `comms_focus` | COMMS right — Message Focus | `comms_focus`, `comms_preview`, comms branch | Top unread + inbox brief; `conversion_count` = `relation="reminded"` lineage edges in the rolling window (`conversion_window_days`) | Open inbox / brief | Open Inbox → `email` | Orbital COMMS right rail |
| `mycelia_activity` | MYCELIA left — Swarm | `agent_activity` (swarm), `mycelia_feed.pulse`, `globe_graph` | Swarm runs + per-agent SENSED/DID pulse + node-kind snapshot | See agents + substrate pulse | Row → `open_task` / source doc | Orbital MYCELIA parity |
| `mycelia_signals` | MYCELIA left — Signals | `mycelia_feed.signals`, `mycelia_feed.health` | Parsed SIGNAL lines (Human/guild) + substrate hygiene strip | Act on swarm asks | Row → `open_note` / `open_doc` | Blackboard consolidation |
| `mycelia_fruit` | MYCELIA right — Fruit | `mycelia_feed.fruit` | Pending-at-gate rows + recent FRUIT entries | Outcome loop | Open ledger → `open_doc` | Herald harvest surface |
| `mycelia_stats` | MYCELIA right — Graph Stats | `globe_graph` meta + nodes | Nodes/edges/by-type + MemPalace status string from search/status bridge. No `kg_query` / `traverse` / `graph_stats` / `find_tunnels` parity — MCP-only, deferred | Graph capacity | Informational; Mycelia deck acts | Orbital MYCELIA right rail |
| `ceo_quick_read` | CORE hero — Quick read | `mycelia_feed.quick_read` | ≤5 scan bullets (Top 3, signals, research, fruit, hygiene) | CEO scan strip | Informational under hero | Ras brief pattern |

---

## Always-on chrome (not toggleable)

| Region | Source | Goal |
|--------|--------|------|
| Brand title / subtitle | Static in payload | Identity |
| Clock + date | Client `setInterval` | Local time context |
| Sync label | `synced_at` from last fetch | Trust freshness; click → Vault Sync |
| Minimize | Client chrome | Dock vault without losing state |
| Domain tabs | Client (`TAB_LAYOUT` + shared `_domainTab` state) | CORE · MEM · PROD · COMMS · AGENCY · RELAY · MYCELIA — a *filter lens* on the HUD view (each still mounts its Orbital-pattern left/right composition), not a competing top-level nav. Visible on desktop always; on mobile, shown only while the HUD tab is active. Orange attention dots when `branch_health` count>0 or busy/attention state. |
| HUD / Queue / Commands / Wire tab bar | Client (`_mobileTab` state) | The one canonical top-level view grouping, shared by desktop and mobile. Desktop shows all four simultaneously via rails so the bar itself is chrome-hidden there; mobile switches between them. Domain tabs filter *within* whichever view is active. |
| Mobile status strip | `status` / `branch_health` | Narrow viewports only, HUD tab only (desktop uses domain tabs instead of a second pill row). Pill tap → domain tab when branch maps to a domain tab. |
| Error banner | Fetch failure state | Surface sync/API problems |

---

## Global hotkeys

Bound once on `document`, active only while the vault is open, silent whenever `_inputOwnsFocus()` is true (typing in a field, Directive Triage open, or any modal that sets `data-cmd-modal-open` on `<body>`).

| Key | Behavior | Implementation |
|-----|----------|-----------------|
| Hold `Space` ≥3s | Arms voice delegate — same as clicking the Audio I/O panel | `static/js/cmdCenterHotkeys.js` (`createSpaceHoldTracker`, unit-tested in `tests/test_cmd_center_hotkeys.mjs`); a quick tap never has its default prevented, only sustained key-repeat does |
| `Esc` | Minimizes/dismisses the vault — same as the minimize button | Calls `_closePanel('down')` directly |

---

## Supporting payload (not separate panels)

These fields feed other components; they are not individually toggleable.

| Key | Feeds | Provenance |
|-----|-------|------------|
| `agenda` | `stage_cards` “Up Next”, plan/morning subtitles | `_build_agenda()` — calendar events, due-soon notes, next task run |
| `notes_preview` | MEM `notes_rail` / `mem_focus` | Newest 16 non-archived notes (title, preview, pinned, tags) |
| `comms_preview` | COMMS `comms_inbox` / `comms_focus` | Recent INBOX via `/api/email/list` path on vault fetch; urgency scores merged from `email_urgency_state_*` when present |
| `comms_focus` | COMMS `comms_focus` panel | Closed-loop conversion: `conversion_count` / `conversion_window_days` / `conversion_since` from `relation="reminded"` edges in `lineage_edges` |
| `jobs_detail` | AGENCY boards, job attention modal, morning card, hero when agency busy | Ready/review lists (with `related_to`), `headline`, and `funnel` `{ingested, evaluated, ready, applied}` — counts are uncapped |
| `relay_board` | RELAY left rail | `{needs_attention, claimed_stuck, in_progress, counts}` — stuck vs attention are distinct; rows may include `stalled` + origin `related_to` |
| `relay_stats` | RELAY right rail | Rolling window (`window_days`, default 7): `issued` · `completed` · `failed` · `open` · `close_rate` (completed/issued, or `null` if none issued) |
| `counts` | Vault Sync card subtitle, vitals deltas, relay stats | Raw counters at build time — includes `handoffs_claimed_stuck` alongside attention / in-progress / job counts |
| `plan_note_id` | Plan Today card `target_id` | `_find_plan_note()` |
| `globe_graph` | Three.js node positions, MYCELIA stats | `fetch_mempalace_globe_graph()` (`mempalace search` preferred, `status` fallback) + `build_globe_graph()` (branch nodes + lineage cross-edges). Not MCP `kg_query`/`traverse` |
| `mycelia_feed` | MYCELIA panels, priority_queue Top 3, hero standby, Quick read, AI Wire SIGNAL lines | `build_mycelia_feed()` — canonical blackboard + spill notes + Fruit Ledger parse |

---

## Lineage (`related_to`)

Cross-object spawn links live in `lineage_edges` (`core/lineage.py`), not per-model FK columns. Writers are fail-soft (log, never break the primary action):

| Relation | Source → target | Written by |
|----------|-----------------|------------|
| `materialized` | job → handoff | Job pipeline materialize |
| `reminded` | email (`account_id:uid`) → note | `action_check_email_urgency` reminder note |
| `promoted` | note → task note | PROD “+ new task” |

**Surface shape on HUD rows:** `related_to: [{kind, id}, ...]` — **1-hop only** (no relation string, no deep walk). Attached on `priority_queue` / `directives`, AGENCY job rows, RELAY board rows (origins filtered to `job`/`note`/`email`), and PROD task cards. Globe adds an undirected edge when both endpoints are already rendered nodes. No historical backfill — only links created after the change shipped.

---

## Stalled-item detection (`stalled`)

Computed **at read time** in `services/home/stalled.py` (`compute_stalled`) — never a persisted DB flag. Thresholds live in one config dict `STALLED_SLA` (conservative defaults; tune after lived-in use).

| Kind | Default SLA signal | `stalled.reason` (examples) |
|------|--------------------|-----------------------------|
| Job | needs-review older than N days | review staleness |
| Handoff | claimed / in-flight older than N hours | `claimed_stuck` |
| Task / prod note | `task_status=in_progress` older than N days | in-progress staleness |
| Note | stale brief / open-item rules (generalizes former `_is_stale_brief`) | brief staleness |
| Email | unread-urgent older than N hours (default 48h) | urgency SLA |

When present, items get `stalled: {since, reason}` and an urgency boost (`apply_stalled_urgency`). **Chain escalation:** if a queue item’s `related_to` neighbor is stalled, the terminal item’s urgency is raised so a healthy-looking child cannot mask a stuck parent (`_escalate_stalled_chain`). RELAY uses the same detector to split `claimed_stuck` from plain `needs_attention`.

---

## Signal priority (dedup)

Every `priority_queue` item carries a `dedup_key` (`"<kind>:<id>"`, e.g. `"handoff:h1"`) and, after `_assign_primary_slots()` runs, a `primary_slot`: `"hero"` when it's the current top-ranked item, `"stage_card:<id>"` or `"deck:<id>"` when another surface already targets it, or `null` otherwise. `hero`, `stage_cards`, and `commands` entries that represent the same item carry the matching `dedup_key`; only the one matching `hero.dedup_key` is flagged `primary` (styled as "act now" — `.cmd-float-card--passive` dims the rest). `suggested_commands` never includes an entry whose `action` equals the current hero's action. **Rule of thumb:** at any moment there is exactly one "next action" surface (the hero); everything else — pills, branch rows, the priority queue itself, non-primary stage cards — is passive/navigable status, never a second competing CTA. The queue itself is never filtered by this — it always lists every directive-worthy item regardless of `primary_slot`.

---

## Priority queue urgency (reference)

Base tiers (before stalled boost / chain floor):

| Source | Urgency | Branch |
|--------|---------|--------|
| Handoffs needing attention | 100 | relay |
| Jobs needing review | 95 | agency |
| Jobs ready to apply | 90 | agency |
| Overdue directive notes | 85 | prod |
| Due-soon directive notes | 80 | prod |
| Pinned directive notes | 70 | prod |
| Other directive notes | 60 | prod |
| Active scheduled tasks | 50 | prod |

Directive notes: pinned, due, or checklist notes/tasks surfaced by `_is_directive_note()`.

**Stalled overlay:** any item with a live `stalled` payload gets `STALLED_SLA["urgency_boost"]` added. If a related neighbor is stalled, `_escalate_stalled_chain` raises the item at least to that neighbor’s escalated tier so the chain surfaces even when the terminal object looks healthy. Stalled in-progress PROD tasks, stuck claimed handoffs, stale review jobs, and unread-urgent email past SLA all enter the queue via this path.

---

## Hero selection order (reference)

1. Handoffs waiting (`relay`) — value = attention count
2. Jobs ready or needs review (`agency`)
3. Top priority-queue directive (`prod` / mixed)
4. Fallback — notes count with “clear deck” explain text

---

## Visibility preferences

- **Storage:** `localStorage['odysseus-cmd-center-visibility']` → `{ [componentId]: boolean }`
- **Default:** missing key = visible (all on)
- **Apply:** `data-cmd-vis="<id>"` on each region; hidden via `[data-cmd-vis][data-cmd-hidden="true"] { display: none !important; }`
- **Settings UI:** gear in top bar → in-vault drawer with toggles + Reset defaults
- **Inspect:** ⓘ on panel headers → Goal / Provenance / Action popover from atlas

## Navigation preference

- **Storage:** `localStorage['odysseus-cmd-view']` → `{ view: 'hud'|'queue'|'commands'|'wire', domainFilter: 'CORE'|'MEM'|'PROD'|'COMMS'|'AGENCY'|'RELAY'|'MYCELIA' }`
- **Default:** missing key = `{ view: 'hud', domainFilter: 'CORE' }`
- **Migration:** if the new key is absent but the legacy `odysseus-cmd-domain-tab` key exists, its value seeds `domainFilter` once (old key is left in place, unused thereafter)
- **Persists across:** tab switches, page reload, reopening the vault — same schema read/written by both desktop and mobile, so resizing the window mid-session doesn't lose the preference

---

## Frontend actions (`_runAction`)

| Action | Opens |
|--------|-------|
| `notes` | Notes panel |
| `open_note` | Specific note |
| `open_doc` | Document editor |
| `library` | Document library |
| `tasks` | Scheduled tasks |
| `open_task` | Task detail |
| `agent_bin` | Handoff inbox |
| `email` | Email inbox |
| `research` | Deep research |
| `calendar` | Calendar |
| `open_session` | Chat session |
| `jobs` | Job attention panel |
| `refresh` | Re-fetch `/api/home/cmd-center` |
| `ceo_brief` | Voice CEO brief flow |
| `run_task` | POST task run (Mycelia) |
| `plan_today` | Plan note or wizard |
| `relay_watcher` | Relay install hint |
