## Why

Every V.A.U.L.T. Command Center tab (CORE, MEM, PROD, COMMS, AGENCY, RELAY, MYCELIA) is read-only presentation today — sort/filter/badge over raw DB rows, concatenated into lists and scored with hand-tuned constants. No object anywhere references another object across kinds: a job that materializes a handoff doc, an urgent email that spawns a reminder note, a note that becomes a task — none of these carry a visible link back to what spawned them. The two surfaces that most look like a real knowledge system turn out to be decorative: `build_globe_graph()` only draws branch→node "star" edges (no note↔task↔handoff↔job edges exist), and the MemPalace bridge doesn't call any of the real graph MCP tools (`kg_query`, `traverse`, `find_tunnels`) — it shells out to a CLI `status` command and regex-parses drawer *counts* into fake nodes. The only genuine staleness/decay logic anywhere is the MEM/PROD stale-brief heuristic; nothing else detects that something has silently stopped moving. This is why the tabs feel like viewers instead of a system: there's no shared mechanism for objects to reference each other, and nothing watches for work that's stalled. The operator wants the command center to actively surface what's in flight, weave related items into visible clusters, and guarantee nothing goes unfinished silently — instead of relying on the operator to notice.

## What Changes

- Introduce a server-owned **lineage backbone**: directive-worthy objects (notes, tasks, handoffs, jobs, email-derived reminders) gain a `related_to: [{kind, id}]` back-reference wherever a real spawn relationship already exists in code today (job→handoff via materialize, urgent-email→reminder-note via `action_check_email_urgency`, note→task via the PROD "+ new task" flow). This is additive metadata on existing rows, not a new entity type.
- Introduce a shared **stalled-item detector**: a per-kind implicit SLA (job needs-review > 3 days, handoff claimed-but-not-complete > N hours, task in-progress with no update > N days, directive note untouched — generalizing the existing stale-brief heuristic) that flags an object and escalates its surfaced urgency wherever it appears, instead of letting it age silently in whatever column it happens to sit in.
- **Fix**: `get_jobs_for_brief()` undercounts `needs_review`/`ready_to_apply` because it takes `len()` of a `list_job_records(limit=5)` query instead of a real count — every downstream consumer (hero, vitals, branch_health) under-reports whenever a bucket exceeds 5.
- **CORE**: `priority_queue` and `globe_graph` consume the lineage backbone so items show their chain and the globe gains real cross-object edges instead of only branch→node stars; stalled-chain items get their own urgency tier.
- **MEM**: notes cluster by lineage + shared tags/topic into visible threads instead of a flat list; the stale-brief heuristic generalizes into an "orphaned thread" detector (open items, untouched N days) surfaced for reap/close/promote-to-task; `mem_focus` becomes a synthesized brief instead of static copy.
- **PROD**: task status (queued/in_progress/blocked/done) moves from client-only `localStorage` onto the actual note/task row so it persists cross-device; "blocked" becomes a real backend state for the first time; stalled in-progress tasks resurface into `priority_queue` instead of silently aging in a board column; tasks display lineage to their originating note/handoff/job.
- **COMMS**: the urgent-email → reminder-note path is wired through the lineage backbone so MEM/PROD can see "this note came from this email"; `comms_focus` tracks a closed-loop rate (urgent emails converted to directives); unread-and-urgent-past-48h escalates via the stalled-item detector.
- **AGENCY**: the pipeline funnel (ingested → evaluated → ready → applied) is surfaced instead of two opaque buckets; job→handoff lineage is exposed explicitly so Agency and Relay visibly connect; stalled-in-review jobs escalate.
- **RELAY**: handoffs surface lineage back to the job/note/directive that spawned them; "claimed but stuck" becomes a distinct state from "needs attention" via the stalled-item detector; `relay_stats` gains an outcome/close-rate view.
- **MYCELIA**: the `swarm-`-prefix/title-substring convention is replaced with an explicit swarm-task registry (real metadata, not string sniffing); `fetch_mempalace_globe_graph`/`build_globe_graph` wire in the real MemPalace MCP graph tools (`kg_query`, `traverse`, `graph_stats`, `find_tunnels`) in place of the CLI-status-parsing fake bridge; this tab becomes the actual visualization surface for the cross-object lineage graph.
- **BREAKING (internal only)**: `commands`/`stage_cards`/`priority_queue` payload items gain a `related_to` field and stalled items gain a `stalled: {since, reason}` field; any frontend code assuming the current shape must tolerate the additions.

## Capabilities

### New Capabilities

- `cmd-center-lineage`: the `related_to` back-reference concept — which object kinds carry it, who writes it (materialize, urgency-reminder, task-creation flows), and how consumers (priority_queue, globe_graph, per-tab panels) read it to show chains instead of isolated items.
- `cmd-center-stalled-item-detection`: the per-kind implicit-SLA rule set, how an object gets flagged `stalled`, and how that escalates its urgency wherever it's surfaced (priority_queue, tab panels, globe_graph).
- `cmd-center-core-system`: CORE's priority_queue/globe_graph consuming lineage + stalled-chain urgency tier.
- `cmd-center-mem-system`: MEM's lineage/tag clustering into threads, orphaned-thread detection, synthesized `mem_focus`.
- `cmd-center-prod-system`: PROD's server-persisted task status (including real `blocked`), stalled in-progress escalation, task lineage display.
- `cmd-center-comms-system`: COMMS's email→note lineage wiring, closed-loop-rate tracking, unread-urgent escalation.
- `cmd-center-agency-system`: AGENCY's corrected pipeline counts, funnel visibility, job→handoff lineage, stalled-review escalation.
- `cmd-center-relay-system`: RELAY's handoff lineage display, claimed-but-stuck distinction, outcome/close-rate stats.
- `cmd-center-mycelia-system`: MYCELIA's explicit swarm-task registry and real MemPalace graph-tool wiring in place of the CLI-status fake bridge.

### Modified Capabilities

- (none — `openspec/specs/` has no existing V.A.U.L.T. capability entries; the sibling in-flight changes `vault-cmd-center-focus-orchestration` and `vault-directive-triage-modal` cover presentation-slot dedup and the triage modal respectively, and are unaffected except that both should read `related_to`/`stalled` fields once this lands rather than treating payload items as flat)

## Impact

- `services/home/cmd_center.py` — lineage read/write plumbing, stalled-item detector, per-tab panel builders (`_build_priority_queue`, `_build_hero`, notes/task/comms/agency/relay/mycelia builders), AGENCY undercount fix.
- `services/home/kg_graph.py` — `build_globe_graph()` gains real cross-object edges from the lineage backbone.
- `services/mempalace/bridge.py` — replace CLI-status regex parsing with real MemPalace MCP graph tool calls (`mempalace_kg_query`, `mempalace_traverse`, `mempalace_graph_stats`, `mempalace_find_tunnels`).
- `routes/home_routes.py` — pass through any new query needs for lineage-joined data.
- `src/job_pipeline/brief.py`, `src/job_pipeline/store.py` — fix `limit=5` undercount; expose pipeline funnel stages and job→handoff lineage.
- `src/handoff_relay.py` — expose lineage (spawning job/note/directive) and claimed-but-stuck timing on handoff rows.
- `src/builtin_actions.py` — `action_check_email_urgency` writes `related_to` on the reminder note it creates.
- `static/js/cmdCenter.js`, `cmdCenterDirective.js` — render lineage chains and stalled badges; PROD board reads/writes server-persisted status instead of `localStorage`.
- `docs/vault-cmd-center-component-atlas.md` — needs a follow-up update once this lands (not part of this change; flagged in design.md).
- `tests/test_home_dashboard.py` — coverage for lineage propagation, stalled-item flagging, and the AGENCY count fix.
