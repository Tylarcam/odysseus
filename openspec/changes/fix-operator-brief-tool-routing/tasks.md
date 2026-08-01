## 1. Shared tool pack

- [x] 1.1 Export or relocate `MORNING_BRIEF_TOOLS` so chat agent routing and the scheduler share one frozenset
- [x] 1.2 Define `OPERATOR_BRIEF_TOOLS` as that set plus `manage_skills` and `web_search`

## 2. Agent intent + domain tools

- [x] 2.1 Add `operator_brief` domain detection patterns in `_classify_agent_request`
- [x] 2.2 Map `operator_brief` → `OPERATOR_BRIEF_TOOLS` in `_DOMAIN_TOOL_MAP` (and domain rules if needed)
- [x] 2.3 Ensure low_signal is false when `operator_brief` matches

## 3. Chat auto-escalation

- [x] 3.1 Add operator-brief patterns to `action_intents.py` so Chat → Agent promotes

## 4. Tests

- [x] 4.1 Test `"Morning Brief"` / focus phrases classify as `operator_brief`, not low_signal
- [x] 4.2 Test operator_brief domain tools are a strict superset of `ALWAYS_AVAILABLE` and include scheduled gather tools
- [x] 4.3 Test `classify_tool_intent` returns needs_tools for Morning Brief
- [x] 4.4 Run the new/related pytest modules and fix failures
