## Why

Users need to bulk-archive stale job pipeline entries (e.g. after accepting another role). `archived` exists as a status but is only set by dedup; `process_job_application` and `/api/jobs` expose no user archive action. The bulk-pipeline-cleanup skill assumes archive works and agents incorrectly fall back to `mark_applied`.

## What Changes

- Add `archive_job` orchestrator transition → `status=archived` with audit event and optional reason (no follow-up task).
- Expose `action=archive` on `process_job_application` and `POST /api/jobs/{job_id}/archive`.
- Update bulk-pipeline-cleanup skill to use `action=archive` (not mark_applied).
- Tests for idempotency, ownership, and tool/API wiring.

## Capabilities

### New Capabilities

- `job-pipeline-archive`: User-initiated archive of job records to terminal `archived` without implying an application was submitted.

### Modified Capabilities

- (none)

## Impact

- `src/job_pipeline/orchestrator.py`
- `src/tool_implementations.py`, `src/tool_schemas.py`, `src/tool_index.py`
- `routes/job_routes.py`
- `data/skills/housekeeping/bulk-pipeline-cleanup/SKILL.md`
- Tests under `tests/`
