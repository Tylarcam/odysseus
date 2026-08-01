## ADDED Requirements

### Requirement: Each directive-worthy item has exactly one primary actionable slot
For every item present in `priority_queue`, `build_cmd_center` SHALL assign a single `primary_slot` value (`"hero"`, `"stage_card:<card_id>"`, `"deck:<command_id>"`, or `null`) representing the one place in the payload where that item is presented as the immediate next action. The assignment SHALL follow the existing urgency ranking already used to build `priority_queue` and `hero` — the top-ranked item's `primary_slot` is `"hero"`.

#### Scenario: Top-ranked handoff owns the hero slot
- **WHEN** a handoff needing pickup is the highest-urgency item in `priority_queue`
- **THEN** that handoff's `dedup_key` matches `hero.dedup_key` and `primary_slot` is `"hero"`

#### Scenario: Lower-ranked item does not also claim the hero slot
- **WHEN** a job ready-to-apply exists but a handoff outranks it in `priority_queue`
- **THEN** the job's `primary_slot` is not `"hero"` and its entry (if present) in `stage_cards` or `suggested_commands` is marked passive rather than duplicating the hero CTA

### Requirement: Non-primary renderings of an item are passive, not competing CTAs
Every payload entry (in `commands`, `suggested_commands`, or `stage_cards`) that represents the same underlying item as another entry SHALL carry a shared `dedup_key`. Entries whose `dedup_key` does not match the current `hero.dedup_key` SHALL still be navigable (clicking still opens the item) but SHALL NOT be labeled or styled as "the next action" — only the primary-slot entry gets that treatment.

#### Scenario: suggested_commands never duplicates the hero action
- **WHEN** `hero.branch` is `"relay"` and `hero.dedup_key` is set
- **THEN** `suggested_commands` SHALL NOT include an entry whose `dedup_key` equals `hero.dedup_key`

#### Scenario: Frontend renders duplicate entries as passive
- **WHEN** the frontend receives a `stage_cards` entry whose `dedup_key` does not match `hero.dedup_key`
- **THEN** `cmdCenter.js` SHALL render that card without primary-CTA styling (no "act now" affordance), while keeping it clickable for navigation

### Requirement: Passive status indicators are exempt from deduplication
Status Pills, `branch_health` rows, and the AI Wire ticker SHALL continue to reflect every relevant item regardless of `primary_slot`, since they are glanceable status surfaces, not action surfaces, and removing an item from them would hide real state rather than reduce redundant CTAs.

#### Scenario: Pill dot still shows even when the item's CTA lives elsewhere
- **WHEN** a handoff's `primary_slot` is `"hero"`
- **THEN** the RELAY status pill SHALL still render its attention dot reflecting that handoff, and the AI Wire SHALL still include its ticker line

### Requirement: Priority queue itself is never filtered by the registry
The `priority_queue` list SHALL always contain every directive-worthy item regardless of `primary_slot` assignment, so the registry never causes an item to become undiscoverable — it only reduces duplicate CTAs in `commands`/`suggested_commands`/`stage_cards`.

#### Scenario: Item suppressed from suggested_commands still appears in the queue
- **WHEN** an item's `dedup_key` matches an existing `hero.dedup_key` and is therefore excluded from `suggested_commands`
- **THEN** that item is still present, unfiltered, in `priority_queue`
