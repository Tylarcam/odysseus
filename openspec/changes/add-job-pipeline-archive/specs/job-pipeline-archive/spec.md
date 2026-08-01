## ADDED Requirements

### Requirement: User can archive a job record

The system SHALL provide a user-initiated archive transition that sets a job record's `status` and `terminal_status` to `archived`, writes a `job_events` row with stage `user_archive`, and MUST NOT schedule follow-up tasks.

#### Scenario: Archive from normalized

- **WHEN** an owner calls archive on a job with status `normalized`
- **THEN** the job status becomes `archived`
- **AND** a job event records `from_status=normalized`, `to_status=archived`, stage `user_archive`

#### Scenario: Archive is idempotent

- **WHEN** an owner archives a job that is already `archived`
- **THEN** the system returns success without creating a duplicate transition error

#### Scenario: Archive does not imply applied

- **WHEN** a job is archived
- **THEN** the system MUST NOT create an applied follow-up scheduled task

### Requirement: Archive is exposed via tool and API

The system SHALL accept archive via `process_job_application` with `action=archive` and via `POST /api/jobs/{job_id}/archive`.

#### Scenario: Tool archive action

- **WHEN** `process_job_application` is called with `action=archive` and a valid `job_id` owned by the caller
- **THEN** the job is archived and the tool returns exit_code 0

#### Scenario: Unknown job

- **WHEN** archive is requested for a missing job_id
- **THEN** the system returns a not-found error
