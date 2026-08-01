## Context

Chat agent tool selection uses `_classify_agent_request()` to detect domains. If no domain matches and the turn is not a continuation, `low_signal=True` skips RAG and leaves only `ALWAYS_AVAILABLE` (`manage_memory`, `ask_user`, `update_plan`). Phrases like "Morning Brief" and "what have we been working on" match no existing domain, so operator briefs fail in chat even though the scheduled Ras Morning Brief task already has a correct allowlist (`MORNING_BRIEF_TOOLS`).

## Goals / Non-Goals

**Goals:**

- Operator brief / focus phrases always get a gather tool pack (never ambient-only).
- Plain Chat auto-escalates to Agent for those phrases.
- Shared constant with the scheduled morning-brief task so chat and cron do not drift.
- Regression tests lock the contract.

**Non-Goals:**

- Rewriting `prompts/ras-morning-brief.md` or Fruit Ledger skill content.
- Building a new UI button (cmd-center "Brief now") — follow-up.
- Changing MCP email connectivity or calendar backends.
- Merging builtin `daily_brief` into the LLM path in this change.

## Decisions

1. **In-session tool pack (not task trigger)**  
   Chat keeps the conversational path: expand tools and let the model write the brief. Triggering the scheduled task would be async/opaque and worse UX for "give me a brief now."  
   Alternative rejected: only call builtin `daily_brief` — loses LLM synthesis and handoff delegation.

2. **New domain `operator_brief`**  
   Add patterns for morning/daily brief, "what's next", "what have we been working on", focus/consensus. Seed `_DOMAIN_TOOL_MAP["operator_brief"]` from a shared frozenset (export `MORNING_BRIEF_TOOLS` or move to `tool_index` / small shared module) plus `manage_skills` and `web_search` for skill load + news.  
   Alternative rejected: stuffing keywords into notes/email domains — incomplete and fragile.

3. **Chat→agent escalation in `action_intents.py`**  
   Mirror other lookup intents so Chat mode is not a silent no-tools trap.  
   Alternative rejected: documenting "use Agent mode" — fails the operator contract.

4. **Honest partial failure stays in prompt territory**  
   If a gather tool fails, existing morning-brief prompt guidance (`⚠️ [tool] failed`) applies when the model loads the skill/prompt; this change only guarantees tools are present.

## Risks / Trade-offs

- [Risk] Broader tool pack increases prompt size for brief turns → Mitigation: pack is already used by scheduled brief; still tiny vs full tool dump.
- [Risk] False positives ("brief me on this PDF") → Mitigation: require brief/focus/consensus phrasing, not bare "brief".
- [Risk] `manage_skills` without skills index in some modes → Mitigation: only useful when agent_mode; harmlessly unused otherwise.

## Migration Plan

- Deploy code + tests; no DB/schema migration.
- Rollback: revert the three source files + tests.

## Open Questions

- None blocking; cmd-center one-click trigger deferred.
