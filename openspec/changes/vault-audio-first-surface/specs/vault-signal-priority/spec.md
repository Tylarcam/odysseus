## MODIFIED Requirements

### Requirement: Passive status indicators are exempt from deduplication

Status Pills, `branch_health` rows, and the AI Wire ticker SHALL reflect every relevant item regardless of
`primary_slot`, but SHALL do so within the salience budget defined by `vault-attention-rationalization`
rather than by restating each item as text. Where the number of relevant items exceeds the surface's
salience budget, these surfaces SHALL collapse to an aggregate count plus sphere state, and SHALL
surface individual items only at the operator's request.

The original exemption held that removing an item from these surfaces "would hide real state rather than
reduce redundant CTAs." That remains true of the *state*, and is why the state is preserved as a count and
as sphere encoding. It is not true of the *textual restatement*, which contributes salience load without
contributing state — a glanceable surface that restates every item as text is not glanceable.

#### Scenario: Pill dot still shows even when the item's CTA lives elsewhere

- **WHEN** a handoff's `primary_slot` is `"hero"`
- **THEN** the RELAY status pill SHALL still render its attention dot reflecting that handoff, and the
  handoff SHALL remain represented in the AI Wire's underlying data

#### Scenario: Passive surface collapses to a count when over budget

- **WHEN** the number of items relevant to a passive surface exceeds that surface's salience budget
- **THEN** the surface SHALL render an aggregate count and corresponding sphere state rather than one
  text line per item

#### Scenario: Collapsed items remain retrievable

- **WHEN** a passive surface has collapsed to an aggregate count
- **THEN** the individual items SHALL remain retrievable on operator request without a new server request

#### Scenario: State is never lost by collapsing

- **WHEN** a passive surface collapses
- **THEN** the presence of the underlying state SHALL still be indicated, so collapsing never makes a
  condition appear absent

## ADDED Requirements

### Requirement: The signal registry governs rail panels, not only command and card arrays

The `dedup_key` / `primary_slot` registry SHALL apply to left-rail and right-rail panel content in
addition to `commands`, `suggested_commands`, and `stage_cards`. A panel entry whose `dedup_key` matches
an entry already presented elsewhere in the current view SHALL be rendered as passive or collapsed rather
than as an independent presentation of the same item.

#### Scenario: Documents are not presented twice in one view

- **WHEN** the same document set would render in both a left-rail and a right-rail panel within the same
  view
- **THEN** only one presentation SHALL be rendered at full emphasis

#### Scenario: Agent activity is not presented three times

- **WHEN** the same underlying agent run would render in a general activity panel, a domain board, and a
  swarm activity panel
- **THEN** at most one SHALL present it at full emphasis and the others SHALL reference or collapse it

#### Scenario: Graph statistics appear once per view

- **WHEN** node and edge counts would render in two panels within the same view
- **THEN** they SHALL render in at most one

### Requirement: A single fact is presented at full emphasis at most once per view

No value SHALL be rendered at full emphasis more than once in a given view, regardless of which panels
would independently choose to render it.

#### Scenario: Attention count is not repeated across hero, glance, queue, and quick-read

- **WHEN** the count of items needing attention would render in the hero directive, the glance chips, the
  priority queue header, and the quick-read summary
- **THEN** it SHALL be rendered at full emphasis in exactly one of them

#### Scenario: Domain wire content is not duplicated across domains in one view

- **WHEN** a wire event is relevant to more than one domain
- **THEN** it SHALL be presented once within the active view rather than once per relevant domain
