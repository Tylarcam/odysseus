## 1. Orchestrator

- [x] 1.1 Add `archive_job(job_id, *, owner=None, reason=None)` with ownership check, idempotent archived, audit event
- [x] 1.2 Do not schedule follow-ups on archive

## 2. Surfaces

- [x] 2.1 Wire `action=archive` in `do_process_job_application` + schema enum + tool index blurb
- [x] 2.2 Add `POST /api/jobs/{job_id}/archive`

## 3. Skill + tests

- [x] 3.1 Update bulk-pipeline-cleanup skill to call `action=archive`
- [x] 3.2 Add pytest coverage for orchestrator + tool
- [x] 3.3 Run related pytest modules
