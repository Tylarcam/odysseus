## Why

Asking Odysseus for a "Morning Brief" (or "what have we been working on") collapses tool access to only `ask_user`, `manage_memory`, and `update_plan` because agent intent treats those phrases as low-signal. The agent then refuses to produce a real brief — unacceptable for an operator workspace whose point is working, not debugging tool gates.

## What Changes

- Classify operator brief / focus / consensus phrases as a first-class agent domain (never low-signal).
- Seed the same gather tool pack used by the scheduled Ras Morning Brief task (notes, calendar, email, handoffs/docs, optional web + skills).
- Auto-escalate plain Chat → Agent when the user asks for a morning brief or focus consensus.
- Add regression tests so `"Morning Brief"` can never resolve to only `ALWAYS_AVAILABLE`.

## Capabilities

### New Capabilities

- `operator-brief-routing`: Deterministic routing so operator brief / focus requests always receive the gather tool pack and agent mode, instead of collapsing to ambient-only tools.

### Modified Capabilities

- (none — no existing main-spec coverage for this routing path)

## Impact

- `src/agent_loop.py` — domain classification + tool seeding
- `src/action_intents.py` — chat→agent auto-escalation patterns
- `src/task_scheduler.py` — reuse / align with `MORNING_BRIEF_TOOLS` (shared constant preferred)
- Tests under `tests/` for intent classification and tool selection
