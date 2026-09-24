## ADDED Requirements

### Requirement: Notes use a three-layer tag taxonomy

The system SHALL encode note organization in `Note.label` as whitespace-separated tokens in three layers:

- Layer 1 scope — exactly one of `scope:daily`, `scope:project`, `scope:research`, `scope:personal`
- Layer 2 intent — zero or one of `intent:feedback`, `intent:review`, `intent:decision`
- Layer 3 topic — zero to three unprefixed kebab-case tokens

The system MUST NOT introduce a workspace table. Workspaces SHALL be filters over Layer 1, optionally combined with Layer 2. A named project SHALL be a Layer 3 topic on a `scope:project` note.

#### Scenario: Canonical encoded label

- **WHEN** a note is scoped to project Hermes with an internal review and topics hermes and jobs
- **THEN** `label` is stored as `scope:project intent:review hermes jobs` (token order: scope, intent, topics sorted)

#### Scenario: Scope is required

- **WHEN** a note is saved without a scope token
- **THEN** the system either assigns `scope:daily` (agent/default path) or rejects the save (explicit UI path that cleared scope)
- **AND** the stored label never contains two scope tokens

#### Scenario: Topic cap

- **WHEN** a save includes more than three topic tokens
- **THEN** the system MUST NOT persist more than three topics
- **AND** the operator is told which topics were dropped or the save is rejected for manual trim

#### Scenario: Collision-safe reserved prefixes

- **WHEN** a topic would otherwise be named `daily` or `review`
- **THEN** reserved meanings remain the prefixed tokens
- **AND** an unprefixed `daily` is treated as a topic, not as scope

### Requirement: Labels bar presents layers as workspaces plus topics

The notes labels bar SHALL group chips into Scope (workspace), Intent, and Topic sections. Synthetic chips (All, Default, Reminders, Goals, Import) remain. Selecting a scope chip SHALL filter notes that carry that `scope:` token.

#### Scenario: Filter by workspace

- **WHEN** the operator clicks the `project` scope chip
- **THEN** only notes with `scope:project` are shown

#### Scenario: Display strips prefixes

- **WHEN** chips render
- **THEN** scope chips show `daily` / `project` / `research` / `personal` without the `scope:` prefix
- **AND** topic chips show `#topic` in kebab-case (or the proper-noun display map)

### Requirement: Conventions are documented

The repository SHALL include `docs/TAG_CONVENTIONS.md` describing the three layers, reserved vocabulary, dedup rules, max-3 topics, and how agents should set `label`.

#### Scenario: Conventions file exists after implementation

- **WHEN** this change is applied
- **THEN** `docs/TAG_CONVENTIONS.md` is present and lists Layer 1, Layer 2, and Layer 3 rules
