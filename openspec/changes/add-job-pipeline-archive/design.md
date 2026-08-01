## Context

Job pipeline state machine already has `archived` for dedup. Close Engine design mentions `declined → archived` but that path was never built. Agents following bulk-pipeline-cleanup hit a dead end.

## Goals / Non-Goals

**Goals:**

- User/agent can archive any owned job to `archived` with an audit event.
- Idempotent if already archived.
- No follow-up tasks; never confuse with `mark_applied`.

**Non-Goals:**

- Hard delete of job rows.
- Approval-batch Close Engine (full declined flow).
- Unarchive / reopen in this change (can follow later).

## Decisions

1. **Orchestrator `archive_job`** — same ownership pattern as `mark_applied`; sets `status=archived` and `terminal_status=archived`; stage `user_archive`; optional `reason` in event detail.
2. **Allow archive from any status including `applied`** — needed to repair mistaken mark_applied without inventing a separate unmark.
3. **Tool + HTTP** — `action=archive` and `POST /api/jobs/{id}/archive?reason=...`.

## Risks / Trade-offs

- [Risk] Archived jobs still in DB → Mitigation: list filters by status; briefs already skip non-attention statuses.
- [Risk] No unarchive → Mitigation: documented non-goal; audit events preserve prior status in `from_status`.
