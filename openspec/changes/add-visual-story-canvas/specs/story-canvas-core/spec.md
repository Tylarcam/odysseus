## ADDED Requirements

### Requirement: Persist story projects
The system SHALL persist story canvas projects as JSON under `data/story_canvas/` and expose list/create/get/update/delete via `/api/story-canvas/projects`.

#### Scenario: Create and reload
- **WHEN** a client POSTs a project payload then GETs by id
- **THEN** the response includes the same nodes and edges

### Requirement: Autosave and undo
The client SHALL autosave after edits and support undo/redo of graph snapshots.

#### Scenario: Undo after move
- **WHEN** the user moves a node then presses Ctrl+Z
- **THEN** the node returns to its previous position
