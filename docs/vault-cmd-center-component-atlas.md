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

---

## Toggleable components

| ID | UI region | Payload key(s) | Provenance | Goal | Function (click) | Rationale |
|----|-----------|----------------|------------|------|------------------|-----------|
| `status_pills` | Top bar + mobile HUD strip | `status`, `branch_health` | `_build_branch_health()` — notes, docs, tasks, handoffs, jobs, voice, swarm counts | Instant branch health | Pill → open that branch surface (`notes`, `tasks`, `agent_bin`, etc.) | Answer “what’s online vs on fire” in one glance |
| `vitals` | Left rail — System Vitals | `vitals[]` | Counts: notes (+pinned), documents, active scheduled tasks, agent-bin attention | Capacity snapshot | Row → `notes` / `library` / `tasks` / `agent_bin` | Honest counters; no fake sparklines |
| `priority_queue` | Left rail — Priority Queue | `priority_queue`, `directives` | `_build_priority_queue()` — urgency: handoffs (100) → jobs review (95) → ready (90) → due/pinned notes → active tasks | What needs you next | Row → `open_note`, `jobs`, or `agent_bin` | Single ranked work list for the day |
| `swarm_activity` | Left rail — Swarm Activity | `agent_activity[]` | Recent `task_runs`, swarm tasks first, last 10 | See agents working | Row → `open_task` | Makes Mycelia visible without opening Tasks |
| `documents` | Left rail — Documents | `documents[]` | 8 newest non-archived documents by `updated_at` | Recent intel / drafts | Row → `open_doc` | Fast path into library artifacts |
| `globe_scene` | Center — Three.js mount | `globe_graph`, `branch_health` | MemPalace KG + branch nodes via `build_globe_graph()` | Spatial system map | Node hover/click → branch action | Situation-room centerpiece |
| `stage_cards` | Center — float cards | `stage_cards[]` | CEO brief, morning/jobs, relay, plan today, vault sync, up-next from agenda | Ritual shortcuts | Card → `ceo_brief`, `jobs`, `agent_bin`, `open_note`, `refresh`, `calendar` | One-tap morning/ops moves |
| `hero` | Center — primary overlay | `hero` | `_build_hero()` — relay → agency jobs → directives → notes | Primary directive | Overlay + CTA → top-ranked action | “Within 5s know what’s on fire” |
| `command_deck` | Right rail — Command Deck | `commands[]`, `suggested_commands[]` | Fixed deck + Mycelia group + hero-branch suggestions | Do something now | Button → `_runAction` | Explicit operator controls |
| `audio_io` | Right rail — Audio I/O | `audio` | Voice stats / standby from builder + live voice UI events | Voice delegate without leaving vault | Click → activate voice agent mode | Hands-free operator loop |
| `ai_wire` | Right rail — AI Wire | `wire[]` | Recent notes, docs, handoffs, jobs, sessions (newest first, max 16) | Live activity ticker | Row → open source item | Traceability — “what just happened” |

---

## Always-on chrome (not toggleable)

| Region | Source | Goal |
|--------|--------|------|
| Brand title / subtitle | Static in payload | Identity |
| Clock + date | Client `setInterval` | Local time context |
| Sync label | `synced_at` from last fetch | Trust freshness; click → Vault Sync |
| Minimize | Client chrome | Dock vault without losing state |
| Mobile tab bar | Client | HUD / Queue / Commands / Wire on narrow viewports |
| Error banner | Fetch failure state | Surface sync/API problems |

---

## Supporting payload (not separate panels)

These fields feed other components; they are not individually toggleable.

| Key | Feeds | Provenance |
|-----|-------|------------|
| `agenda` | `stage_cards` “Up Next”, plan/morning subtitles | `_build_agenda()` — calendar events, due-soon notes, next task run |
| `jobs_detail` | Job attention modal, morning card, hero when agency busy | Jobs pipeline service |
| `counts` | Vault Sync card subtitle, vitals deltas | Raw counters at build time |
| `plan_note_id` | Plan Today card `target_id` | `_find_plan_note()` |
| `globe_graph` | Three.js node positions | `fetch_mempalace_globe_graph()` + `build_globe_graph()` |

---

## Priority queue urgency (reference)

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
