## ADDED Requirements

### Requirement: Lineage edges are recorded when one directive-worthy object spawns another
When backend code creates a note, handoff, or job-derived artifact from an existing object (job→handoff materialization, urgent-email→reminder-note, note→task promotion), the system SHALL record a lineage edge linking the new object back to its source, using a generic `(source_kind, source_id, target_kind, target_id, relation)` record rather than a per-model foreign-key column.

#### Scenario: Job materializes a handoff document
- **WHEN** `job_pipeline` materializes a handoff document from a `JobRecord` ready to apply
- **THEN** the system SHALL record a lineage edge with `source_kind="job"`, `source_id=<job id>`, `target_kind="handoff"`, `target_id=<new handoff note id>`, `relation="materialized"`

#### Scenario: Urgent email spawns a reminder note
- **WHEN** `action_check_email_urgency` creates a reminder note for a UID scored urgent
- **THEN** the system SHALL record a lineage edge with `source_kind="email"`, `source_id="<account_id>:<uid>"`, `target_kind="note"`, `target_id=<reminder note id>`, `relation="reminded"`

#### Scenario: Lineage write never blocks the primary action
- **WHEN** the lineage edge write fails for any reason (DB error, unexpected kind)
- **THEN** the primary action (materializing the handoff, creating the reminder note) SHALL still succeed and the failure SHALL be logged, not raised to the caller

### Requirement: Consumers can resolve lineage for a batch of objects without N+1 queries
Any cmd-center panel builder that renders a set of objects (priority queue, globe graph, per-tab lists) SHALL be able to fetch lineage edges for that whole batch in a single query keyed by the already-known ids, rather than querying per-item.

#### Scenario: Priority queue renders chain context
- **WHEN** `_build_priority_queue()` assembles its ranked list of handoffs/jobs/notes/tasks
- **THEN** it SHALL attach a `related_to` field (list of `{kind, id}`, at most the immediate parent) to each item using one batched lineage lookup for the whole list

### Requirement: Lineage is additive-only, no historical backfill
The system SHALL NOT attempt to retroactively infer or backfill lineage edges for objects that existed before this capability shipped.

#### Scenario: Pre-existing handoff has no lineage
- **WHEN** a handoff note created before this capability shipped is rendered
- **THEN** its `related_to` SHALL be an empty list rather than a guessed/fuzzy-matched link
