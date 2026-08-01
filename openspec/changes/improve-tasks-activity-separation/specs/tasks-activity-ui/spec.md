## ADDED Requirements

### Requirement: Visually bounded activity entries
Each Tasks Activity run SHALL render as a visually distinct card with padding, a border, a subtle background, and a left accent derived from the row’s `--cat-hue` CSS variable when present.

#### Scenario: Consecutive runs are separable
- **WHEN** the Activity tab shows two or more task runs in `#tasks-activity-list`
- **THEN** each `.task-log-row` is visually bounded so an operator can tell where one entry ends and the next begins without reading timestamps alone

#### Scenario: Category accent is visible
- **WHEN** a `.task-log-row` has `--cat-hue` set inline
- **THEN** the row shows a left accent stripe using that hue

### Requirement: List gap between activity cards
The Activity list SHALL space cards with a gap larger than Memory’s default `.memory-list` gap so multi-line bodies do not visually merge.

#### Scenario: Gap between cards
- **WHEN** two `.task-log-row` elements are adjacent in `#tasks-activity-list`
- **THEN** there is a clear vertical gap (approximately 8–10px) between their card boundaries

### Requirement: Head body actions hierarchy
Each non-skipped activity card SHALL present a header row (status, icon, name, time), a body for the run result, and an actions row, with spacing that keeps body and actions visually attached to their own header.

#### Scenario: Body belongs to its header
- **WHEN** a run has a result body
- **THEN** the body appears inside the same card as that run’s header, not as floating text between cards

### Requirement: Skipped rows stay slim
Skipped (noop) activity rows SHALL remain a compact, dimmed single-line presentation without a result body or action chrome.

#### Scenario: Skipped entry presentation
- **WHEN** a run has status `skipped`
- **THEN** the row renders as a slim `.task-log-row.is-skipped` card with lower visual weight than a full result card

### Requirement: Long bodies collapse until expanded
Long activity results SHALL be visually collapsed by default and expand when the row is marked expanded or the operator uses the existing show-more control.

#### Scenario: Long result collapsed by default
- **WHEN** a `.task-log-row` has class `is-long` and does not have class `expanded`
- **THEN** the `.task-log-row-body` is height-clamped with overflow hidden

#### Scenario: Expanded long result
- **WHEN** the operator expands a long row (row click or Show more)
- **THEN** the full body is visible within the same card
