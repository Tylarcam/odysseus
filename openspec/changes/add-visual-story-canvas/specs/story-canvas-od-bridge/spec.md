## ADDED Requirements

### Requirement: Export selection to Open Design
The system SHALL provide an export path that packages a selected subgraph (nodes, edges, asset refs, brief text) for Open Design consumption via filesystem brief and/or `od` MCP tools, applying an optional DESIGN.md brand contract.

#### Scenario: Export brief package
- **WHEN** the user exports a selection with a DESIGN.md id
- **THEN** the system produces a brief package containing titles, bodies, image refs, and edge relationships suitable for OD Studio artifact generation

### Requirement: Non-blocking without OD
The Story Canvas SHALL remain fully usable when Open Design is not installed; export MAY degrade to a downloadable JSON/Markdown brief.

#### Scenario: Offline export
- **WHEN** Open Design MCP is unavailable
- **THEN** the user can still download a story brief of the selection
