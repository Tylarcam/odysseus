## ADDED Requirements

### Requirement: Paste and upload images
The board SHALL accept clipboard paste and file upload of images as Image nodes with provenance metadata.

#### Scenario: Clipboard paste
- **WHEN** the user pastes an image while on the canvas view
- **THEN** a new Image node appears near the viewport center with provenance noting clipboard

### Requirement: Unified entry modes
The composer SHALL create Text, Beat, Prompt, or Research nodes from a single text entry.

#### Scenario: Research mode
- **WHEN** the user submits a query in Research mode
- **THEN** an editable Research Context node is created (not a read-only chat message)
