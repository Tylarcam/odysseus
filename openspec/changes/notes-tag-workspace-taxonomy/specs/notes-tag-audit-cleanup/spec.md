## ADDED Requirements

### Requirement: Audit produces a complete tag inventory before any write

A read-only audit SHALL enumerate every distinct tag across owned notes, count notes per tag, list untagged notes, list singletons, and cluster tags by proposed layer (scope / intent / topic). The audit MUST NOT modify `Note` rows.

#### Scenario: Inventory output

- **WHEN** the audit script runs
- **THEN** it writes a baseline unique-tag count, per-tag frequencies, singleton list, and untagged note ids
- **AND** it writes a draft mapping file (current token → canonical token or `drop`)

#### Scenario: No workspace table

- **WHEN** the audit looks for workspaces
- **THEN** it reports that workspaces are not a first-class entity
- **AND** it treats existing tags that function as fake workspaces (e.g. `Work`) as candidates for `scope:project` plus a topic, not as a new table

### Requirement: Dedup rules apply without asking

The mapping SHALL merge tokens case-insensitively, merge obvious singular/plural pairs, and apply the synonym list (`interview-prep` → `interview`, `sac` → `search-as-code`). Project display names MAY title-case (`hermes` stored, Hermes displayed).

#### Scenario: Case merge

- **WHEN** notes use `Approval` and `approval`
- **THEN** the mapping emits a single canonical topic `approval`

#### Scenario: Abbreviation merge

- **WHEN** notes use `sac`
- **THEN** the canonical topic is `search-as-code`

### Requirement: Migration is sign-off gated and reversible

The migrate tool SHALL refuse to write unless a mapping file is provided and `--apply` is set. Before the first UPDATE it MUST write a backup of `{id, label}` for every affected note. `--restore` SHALL put those labels back. Notes whose mapped topic list still exceeds three SHALL be skipped and listed for manual review. Untagged notes SHALL receive `scope:daily` only.

#### Scenario: Dry-run does not write

- **WHEN** migrate runs without `--apply`
- **THEN** no `Note.label` values change
- **AND** a projected unique-tag count is printed against the audit baseline

#### Scenario: Apply writes backup first

- **WHEN** migrate runs with `--apply` and an approved map
- **THEN** a JSON backup is written before any UPDATE
- **AND** every migrated note has exactly one scope token and at most three topics

#### Scenario: Restore

- **WHEN** migrate `--restore` is given that backup file
- **THEN** each note’s `label` returns to the backed-up value

#### Scenario: Over-cap notes are not auto-trimmed

- **WHEN** a note still has four or more topics after mapping
- **THEN** that note is not updated
- **AND** it appears in a needs-review list

### Requirement: Unique tag count drops by at least 30 percent

After a successful `--apply`, the count of distinct tokens in `Note.label` (after prefix-aware parse) MUST be ≤ 70% of the audit baseline. If the projection misses that target, migrate MUST abort unless an explicit override flag is passed.

#### Scenario: Target miss aborts

- **WHEN** the dry-run projects less than 30% reduction
- **THEN** `--apply` refuses without an override

#### Scenario: Singletons

- **WHEN** a tag appears on exactly one note and is not a kept project name
- **THEN** the mapping merges it into an existing topic or drops it
- **AND** the note itself is not deleted
