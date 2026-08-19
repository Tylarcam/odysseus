## ADDED Requirements

### Requirement: A single focus object is the shared referent between voice and the sphere

The vault SHALL maintain exactly one focus object at a time, carrying `focused_entity`, `focused_edge`,
`focus_source` (one of `voice`, `click`, `agent`, `search`), `focus_confidence`, and `focus_timestamp`.
All speech and all sphere highlighting SHALL read from this object rather than maintaining independent
notions of what is currently under discussion.

#### Scenario: Clicking a node sets focus with click provenance

- **WHEN** the operator clicks a sphere node
- **THEN** the focus object SHALL be updated with that entity and `focus_source` of `click`

#### Scenario: Agent reference sets focus with agent provenance

- **WHEN** the agent begins speaking about a specific entity
- **THEN** the focus object SHALL be updated with that entity and `focus_source` of `agent`

#### Scenario: Only one focus is held at a time

- **WHEN** focus moves from one entity to another
- **THEN** the previous entity SHALL no longer be the focused entity

### Requirement: Focus changes by the operator take precedence over agent focus mid-utterance

When `focus_source` transitions to `click`, `voice`, or `search` while the agent is speaking about a
different entity, the system SHALL treat the operator's focus as authoritative and SHALL NOT silently
continue highlighting the agent's prior referent.

#### Scenario: Operator clicks away while the agent is talking

- **WHEN** the agent is mid-utterance about entity A and the operator clicks entity B
- **THEN** the focus object SHALL hold entity B with `focus_source` of `click`, and sphere highlighting
  SHALL follow entity B

#### Scenario: Agent does not overwrite fresh operator focus

- **WHEN** the operator has set focus within the current turn and the agent attempts to set focus to a
  different entity
- **THEN** the operator's focus SHALL be preserved for the remainder of the turn

### Requirement: Speech and sphere highlighting are bidirectionally bound at all times

The binding between spoken content and sphere node highlighting SHALL be active during all voice
interaction, not only during scripted brief playback. Speaking about an entity SHALL highlight it, and
selecting an entity SHALL make it available as the subject of the next spoken turn.

#### Scenario: Highlighting is active outside brief playback

- **WHEN** the agent speaks about an entity during ordinary interaction with no brief in progress
- **THEN** the corresponding sphere node SHALL be highlighted

#### Scenario: Selection becomes the spoken subject

- **WHEN** the operator selects a sphere node and then issues a voice command containing a deictic
  reference such as "this one"
- **THEN** the command SHALL resolve against the focused entity

### Requirement: The sphere renders a degree-of-interest view rather than the full graph

The sphere SHALL render the focused entity, its first-order neighbors, and a reduced-emphasis context
shell for the remainder. It SHALL NOT render all nodes at equal emphasis.

#### Scenario: Neighbors are emphasized over distant nodes

- **WHEN** an entity is focused
- **THEN** its first-order neighbors SHALL render at full emphasis and non-neighbors SHALL render at
  reduced emphasis

#### Scenario: Context is retained, not removed

- **WHEN** the view is culled to the focused neighborhood
- **THEN** a reduced-emphasis representation of the wider graph SHALL remain visible so overall scale
  stays apparent

### Requirement: Sphere nodes encode operational state, and never by colour alone

Node appearance SHALL encode operational state (including at least blocked, stale, and
awaiting-approval), urgency, dependency direction, and entity type. State SHALL be distinguishable by at
least one channel in addition to colour.

#### Scenario: A blocked entity is visually distinct

- **WHEN** an entity is blocked
- **THEN** its node SHALL be distinguishable from an unblocked node by a non-colour channel such as
  shape, outline, or motion, in addition to any colour difference

#### Scenario: Dependency direction is visible

- **WHEN** one entity blocks another
- **THEN** the edge between them SHALL indicate direction

### Requirement: Addressable sphere nodes carry numeric verbal handles

Nodes available for selection SHALL be assigned stable, visible numeric handles within the current view,
and the system SHALL resolve a spoken handle to the corresponding node.

#### Scenario: Spoken number selects a node

- **WHEN** three nodes are addressable and the operator says "open three"
- **THEN** the node bearing handle 3 SHALL become the focused entity

#### Scenario: Handles remain stable within a view

- **WHEN** the view has not changed
- **THEN** a given node SHALL retain the same numeric handle across successive renders

### Requirement: The sphere maintains a stable orientation cue

Because the sphere is a three-dimensional layout, it SHALL present a persistent orientation reference so
the operator can re-establish spatial bearing after rotation.

#### Scenario: Orientation is recoverable after rotation

- **WHEN** the operator has rotated the sphere away from its default orientation
- **THEN** an orientation cue SHALL remain visible, and a means to return to the default orientation
  SHALL be available
