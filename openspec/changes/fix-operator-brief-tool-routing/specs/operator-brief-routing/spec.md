## ADDED Requirements

### Requirement: Operator brief phrases are never low-signal

The system SHALL classify user messages that request a morning/daily brief, today's focus, or a "what have we been working on / what's next / consensus" style operator summary as an `operator_brief` domain. Such turns MUST NOT be treated as low-signal ambient-only turns.

#### Scenario: Morning Brief is operator_brief

- **WHEN** the latest user message is "Morning Brief" (case-insensitive)
- **THEN** agent intent classification includes domain `operator_brief` and `low_signal` is false

#### Scenario: Focus consensus phrase is operator_brief

- **WHEN** the latest user message is "what have we been working on" or "what's next today"
- **THEN** agent intent classification includes domain `operator_brief` and `low_signal` is false

### Requirement: Operator brief turns receive the gather tool pack

When domain `operator_brief` is active, the system SHALL seed the agent's relevant tools with at least: `manage_notes`, `manage_calendar`, `list_emails` (and/or MCP email list), `app_api`, document create/update/manage tools, `manage_skills`, and `web_search`. The selected set MUST be a strict superset of `ALWAYS_AVAILABLE` (not equal to it).

#### Scenario: Morning Brief tool set is not ambient-only

- **WHEN** the user asks for a Morning Brief in agent mode
- **THEN** the tools advertised to the model include notes, calendar, and email gather tools
- **AND** the tool set is not limited to only `manage_memory`, `ask_user`, and `update_plan`

### Requirement: Chat mode auto-escalates for operator brief requests

When the user is in plain Chat mode and sends an operator-brief phrase, the system SHALL promote the turn to Agent mode so tools are available.

#### Scenario: Chat Morning Brief escalates

- **WHEN** chat mode is `chat` and the message matches an operator-brief intent pattern
- **THEN** the request is handled as agent mode with tools enabled

### Requirement: Shared allowlist with scheduled Morning Brief

The chat operator-brief gather pack SHALL reuse the same core tool names as the scheduled Ras Morning Brief allowlist (`MORNING_BRIEF_TOOLS`), so chat and cron cannot silently diverge on gather capability.

#### Scenario: Shared constant covers scheduled tools

- **WHEN** `MORNING_BRIEF_TOOLS` is defined for the scheduled task
- **THEN** the `operator_brief` domain tool map includes every name in that set (MCP email name included when present in the set)
