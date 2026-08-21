## ADDED Requirements

### Requirement: One graph, multiple views
The system SHALL render the same project nodes in Canvas, Outline, Storyboard, and Present views ordered by `sequenceIndex` without duplicating content records.

#### Scenario: Reorder reflects everywhere
- **WHEN** the user changes a node's sequence index
- **THEN** Outline and Storyboard order update to match

### Requirement: Typed connections
The canvas SHALL support typed edges among at least: follows, supports, references, visualReference, researchContext.

#### Scenario: Connect with type
- **WHEN** the user connects out-port to in-port with edge type "researchContext"
- **THEN** the edge is stored with that type and drawn on the canvas
