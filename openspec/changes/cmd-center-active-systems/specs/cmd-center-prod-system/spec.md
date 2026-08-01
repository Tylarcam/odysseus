## ADDED Requirements

### Requirement: Task status is persisted server-side, including a real "blocked" state
`notes.task_status` (`queued|in_progress|blocked|done`) and `notes.task_status_at` SHALL be the source of truth for a PROD task's board column, replacing the client-only `localStorage` maps. "Blocked" SHALL be representable and readable from the server for the first time.

#### Scenario: Task marked blocked on one device is blocked on another
- **WHEN** an operator marks a task `blocked` in the browser on one device
- **THEN** opening the vault on a different device SHALL show the same task as `blocked`

#### Scenario: Existing localStorage state is backfilled once
- **WHEN** the frontend loads a task that has a `localStorage` status entry but no server `task_status`
- **THEN** it SHALL POST the local status to the server once and thereafter treat the server field as authoritative for that task

### Requirement: Stalled in-progress tasks resurface into the priority queue
A task whose `task_status` is `in_progress` and whose `task_status_at` is older than the configured stalled-task threshold (per `cmd-center-stalled-item-detection`) SHALL appear in CORE's `priority_queue` with elevated urgency, rather than only being visible by opening the PROD board.

#### Scenario: Task idle for the threshold period escalates
- **WHEN** a task has been `in_progress` with no `task_status_at` update for longer than the configured threshold
- **THEN** it SHALL appear in `priority_queue` even if it is not due/pinned

### Requirement: Tasks display lineage to their originating object
A PROD task card SHALL show its `related_to` parent (note, handoff, or job) when one exists, per `cmd-center-lineage`.

#### Scenario: Task promoted from a note shows its origin
- **WHEN** a task was created via the PROD "+ new task" flow from an existing note
- **THEN** its task card SHALL display a reference back to that originating note
