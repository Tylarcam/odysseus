## ADDED Requirements

### Requirement: Job bucket counts reflect true totals, not a capped query length
`get_jobs_for_brief()` SHALL report `needs_review_count` and `ready_to_apply_count` as true counts of matching `JobRecord`s, independent of the `limit=5` used for the row list actually displayed.

#### Scenario: More than 5 jobs need review
- **WHEN** 8 jobs currently have `attention="needs_review"`
- **THEN** `needs_review_count` SHALL be `8`, and the displayed row list MAY still be capped to 5 rows

### Requirement: The job pipeline funnel is surfaced, not just two terminal buckets
AGENCY's payload SHALL expose counts for each pipeline stage (ingested, evaluated, ready, applied) rather than only `needs_review`/`ready_to_apply`.

#### Scenario: Operator sees the whole funnel
- **WHEN** the AGENCY payload is built
- **THEN** it SHALL include a stage-count breakdown covering ingested/evaluated/ready/applied, sourced from `job_pipeline` state

### Requirement: Jobs expose lineage to the handoff they materialize
When a job produces a handoff document, the job's payload entry SHALL include a `related_to` reference to that handoff (per `cmd-center-lineage`), so AGENCY and RELAY visibly connect.

#### Scenario: Job ready-to-apply shows its handoff
- **WHEN** a job has already materialized a handoff document
- **THEN** its AGENCY row SHALL include `related_to: [{kind: "handoff", id: <handoff note id>}]`

### Requirement: Jobs stalled in review escalate
A job whose `attention` has been `needs_review` longer than the configured SLA (per `cmd-center-stalled-item-detection`) SHALL be flagged stalled and surfaced at elevated urgency in `priority_queue`.

#### Scenario: Job sits in review for 4 days
- **WHEN** a job has been in `needs_review` for more than 3 days
- **THEN** it SHALL be flagged `stalled` and appear in `priority_queue` at elevated urgency
