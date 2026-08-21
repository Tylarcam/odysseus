## ADDED Requirements

### Requirement: Research creates editable context
The composer Research mode SHALL create a Research node with editable claims, notes, and sources—not a one-shot chat answer.

#### Scenario: Research drop
- **WHEN** the user submits a query in Research mode
- **THEN** a Research node appears with query, editable claims, and sources fields

### Requirement: Library and session hydration
The system SHALL be able to seed or hydrate Research/Source nodes from Odysseus deep research library listings and from a concrete `session_id` report payload.

#### Scenario: Hydrate by session id
- **WHEN** the user drops or enters a deep_research session id
- **THEN** the Research node body includes title, query excerpt, and source URLs from that report when available
