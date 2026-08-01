## ADDED Requirements

### Requirement: Each object kind has an implicit SLA that defines "stalled"
The system SHALL define, per object kind, a threshold past which an object with no forward progress is considered stalled: a job in `needs_review` longer than 3 days, a handoff `claimed` but not `complete`/`failed` longer than a configurable N hours, a task `in_progress` with no `task_status_at` update longer than a configurable N days, and a directive note untouched past its existing stale-brief heuristic. Thresholds SHALL live in one configuration location, not scattered per-caller constants.

#### Scenario: Job stuck in review escalates
- **WHEN** a `JobRecord` has been in `needs_review` for more than 3 days
- **THEN** the system SHALL mark it `stalled: {since, reason: "needs_review_sla"}` when building AGENCY's payload

#### Scenario: Handoff claimed but never completed
- **WHEN** a handoff's `handoff_relay_status` has been `running` (claimed) for longer than the configured stuck-hours threshold with no transition to `complete`/`failed`
- **THEN** the system SHALL mark it `stalled: {since, reason: "claimed_stuck"}`, distinct from the existing `needs_attention` bucket

### Requirement: Stalled status is computed fresh on every read, not persisted
The system SHALL compute stalled status as a pure function of current object state and the current time at each `build_cmd_center()` call, and SHALL NOT write a persisted `stalled` flag to the database.

#### Scenario: Object recovers before next poll
- **WHEN** a stalled task receives a status update before the next poll
- **THEN** the next `build_cmd_center()` call SHALL no longer mark it stalled, with no manual "unstall" action required

### Requirement: Stalled items escalate urgency wherever they are surfaced
When an object is flagged stalled, its surfaced urgency in `priority_queue` and any tab-specific panel SHALL increase relative to an equivalent non-stalled item of the same kind, so it does not silently continue aging in whatever column or bucket it already occupies.

#### Scenario: Stalled task resurfaces into the priority queue
- **WHEN** a PROD task has been `in_progress` with no update for longer than the configured threshold
- **THEN** it SHALL appear in `priority_queue` with elevated urgency even though it was not previously due/pinned/active-only ranked there
