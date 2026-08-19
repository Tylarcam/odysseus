## ADDED Requirements

### Requirement: Attention stack payload
The CMD Center API SHALL include an `attention_stack` array of items that need operator triage (handoffs needing attention, jobs needing review or ready to apply, and overdue directive notes), ordered highest urgency first.

#### Scenario: Overdue notes appear in stack
- **WHEN** the operator has one or more overdue directive notes and no higher-urgency handoffs/jobs
- **THEN** each overdue note SHALL appear in `attention_stack` with `kind` `note`, `status` `overdue`, and a relative `due_label`

#### Scenario: Handoffs rank above overdue notes
- **WHEN** handoffs need attention and overdue notes also exist
- **THEN** handoff items SHALL appear before overdue notes in `attention_stack`

### Requirement: Directive triage modal open
When `attention_stack` is non-empty, activating the vault primary directive control (hero surface or its CTA) SHALL open the Directive Triage modal showing the first stack card. It MUST NOT jump directly to Notes/Jobs/Agent Bin for that activation.

#### Scenario: Open with items waiting
- **WHEN** the operator activates the primary directive control and `attention_stack.length > 0`
- **THEN** the system SHALL display the triage modal with the top card’s title and status chip

#### Scenario: Empty stack
- **WHEN** the operator activates the primary directive control and `attention_stack` is empty
- **THEN** the system SHALL NOT open the triage modal and MAY fall back to the previous standby action

### Requirement: Swipe left delegates via Relay handoff
On a mobile viewport, a horizontal swipe left on the active triage card (or activating Delegate) SHALL create an Agent Bin / Relay handoff document for that item using the shared handoff helper, then advance to the next card after success.

#### Scenario: Delegate a note
- **WHEN** the operator swipes left (or taps Delegate) on a note card
- **THEN** the system SHALL create a handoff document via `createHandoffDocument` and remove that card from the visible stack after success

#### Scenario: Delegate an existing handoff card
- **WHEN** the active card `kind` is `handoff`
- **THEN** the system SHALL open Agent Bin for that item instead of creating a duplicate handoff packet

### Requirement: Swipe right marks finished
On a mobile viewport, a horizontal swipe right on the active triage card (or activating Done) SHALL mark the item finished using the kind-appropriate API, then advance to the next card after success.

#### Scenario: Finish an overdue note
- **WHEN** the operator swipes right (or taps Done) on an overdue note card
- **THEN** the system SHALL archive or clear that note’s due state via the notes API and advance the stack

#### Scenario: Finish a job card
- **WHEN** the operator completes Done on a job card
- **THEN** the system SHALL call the jobs mark-applied (or equivalent dismiss) API and advance the stack

### Requirement: Desktop button parity
On desktop viewports, the triage modal SHALL expose Delegate, Done, and Open controls that perform the same actions as swipe left, swipe right, and opening the item’s native surface without removing it until Done succeeds.

#### Scenario: Open without finishing
- **WHEN** the operator activates Open on a card
- **THEN** the system SHALL open the item via the existing CMD Center action map and MUST leave the card in the stack until Done or Delegate succeeds

### Requirement: Double-tap peeks the next card
On a mobile viewport, a double-tap on the active triage card (without a qualifying horizontal swipe) SHALL show the next stack item without delegating or marking it finished. The peeked-past item MUST remain in the stack. After the last card, the next peek SHALL wrap to the first card.

#### Scenario: Peek without finishing
- **WHEN** the operator double-taps a card and the gesture is not a horizontal swipe
- **THEN** the system SHALL show the next card and MUST NOT create a handoff or call a finish API

#### Scenario: Wrap the deck
- **WHEN** the operator peeks the last card in a stack of two or more
- **THEN** the system SHALL show the first card again with that item still in the stack

#### Scenario: Swipe still wins
- **WHEN** a touch sequence is a horizontal swipe past threshold
- **THEN** the system SHALL delegate or finish as today and MUST NOT treat that sequence as a peek

### Requirement: Post-action refresh
After a successful Delegate or Done action, the vault SHALL refresh CMD Center data so hero counts, `attention_stack`, and related HUD panels reflect the new state.

#### Scenario: Last card completed
- **WHEN** the operator finishes or delegates the final card in the stack
- **THEN** the modal SHALL close and the hero attention count SHALL update on refresh
