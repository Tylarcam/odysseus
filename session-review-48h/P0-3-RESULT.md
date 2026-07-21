# P0#3 Result — CEO brief cron race (`eb3d2499`)

**Status:** Done  
**Agent:** C  
**Date:** 2026-07-09

## Root cause

`ceo_brief` default cron was `30 7 * * *` (07:30), but the morning swarm harvest it reads runs later:

| Producer | Schedule (seed_swarm, America/New_York) | Output brief harvests |
|----------|------------------------------------------|------------------------|
| Sporangium AM | daily 07:00 | Swarm Plan / blackboard |
| Spore | daily 07:40 | inbound substrate |
| Rhizo | daily 08:30 | Research Brief — {date} |

At 07:30 the brief often composed with empty “No Swarm Plan / Rhizo hasn’t filed…” sections because Sporangium may still be running and Spore/Rhizo had not started.

## Fix (minimal)

1. **Delay cron** to `0 9 * * *` (after Rhizo 08:30), with `old_cron_expressions: ["30 7 * * *"]` so existing DB rows migrate on housekeeping sync.
2. **Generalize** `old_cron_expressions` migration in housekeeping (was hard-coded to `check_email_urgency` only).
3. **Gate** scheduled `action_ceo_brief` runs: if today’s Swarm Plan / Research Brief docs are missing before soft deadline hour 10, raise `TaskDeferred` (15 min) so the scheduler retries. Manual CMD Center runs (no `task_name`) are not deferred.
4. **Propagate** `TaskDeferred` from `_execute_action` (same path as `TaskNoop`).

## Files changed

| File | Change |
|------|--------|
| `src/task_scheduler.py` | cron `0 9 * * *` + invariant comment; generalize old-cron migrate; re-raise `TaskDeferred` |
| `src/builtin_actions.py` | `ceo_brief_morning_harvest_ready()` + scheduled harvest gate |
| `tests/test_ceo_brief_harvest_gate.py` | cron + gate unit tests (4) |
| `session-review-48h/P0-3-RESULT.md` | this report |

## How to verify

```bash
python -m pytest tests/test_ceo_brief_harvest_gate.py -q
```

Expect: `4 passed`.

Also after app restart / housekeeping seed for an owner:

- DB `scheduled_tasks` row with `action=ceo_brief` should show `cron_expression = '0 9 * * *'` (migrated from `30 7 * * *` if present).
- Logs may show `Task 'CEO Brief…' deferred … morning harvest not ready` if fired early with empty harvest before hour 10.

## Out of scope (per plan)

- Ideal morning loop rewrite  
- Wiring `prompts/executive-brief-template.md` (P2)  
- Archivist / Clicky / gateway restarts  
