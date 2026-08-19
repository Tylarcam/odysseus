## ADDED Requirements

### Requirement: Every item in the attention layer carries a consequence, a response time, and an operator action

`build_cmd_center` SHALL emit, for every item it presents in the attention layer, the fields
`consequence` (what happens if ignored), `response_time` (how long the operator has), and
`operator_action` (the distinct action available). An item for which any of these three cannot be
supplied SHALL NOT be assigned a salience tier and SHALL be emitted as detail instead.

This is the gate that prevents density regrowth: a new panel cannot enter the attention layer by being
added to a rail, only by satisfying this test.

#### Scenario: A failed handoff qualifies for the attention layer

- **WHEN** a relay handoff has `handoff_relay_status` of `failed`
- **THEN** the payload entry SHALL carry a non-empty `consequence`, a `response_time`, and an
  `operator_action`, and SHALL be assigned a salience tier

#### Scenario: A close-rate metric does not qualify

- **WHEN** `relay_stats` computes a rolling close rate of 67%
- **THEN** that value SHALL be emitted as detail with no salience tier, because no distinct operator
  action exists for it

#### Scenario: An all-zero counter does not qualify

- **WHEN** `relay_stats` reports `waiting: 0`, `stuck: 0`, and `in_flight: 0`
- **THEN** none of those values SHALL be assigned a salience tier

### Requirement: At most three salience tiers exist, with a bounded top tier

The payload SHALL define exactly three salience tiers. `build_cmd_center` SHALL target a distribution of
approximately 80% lowest tier, 15% middle tier, and 5% top tier across items in the attention layer, and
SHALL cap the top tier at no more than three concurrent items.

#### Scenario: Top tier is capped at three items

- **WHEN** five items each independently satisfy the top-tier urgency criteria
- **THEN** at most three SHALL be assigned the top tier, and the remainder SHALL be assigned the middle
  tier

#### Scenario: No fourth tier is introduced

- **WHEN** any item is assigned a salience tier
- **THEN** the value SHALL be one of exactly three defined tier identifiers

### Requirement: Non-qualifying items are reclassified as detail, never removed

An item that fails the rationalization test SHALL remain present in the payload and SHALL remain
reachable by the operator. Reclassification changes only whether the item occupies resting salience.

#### Scenario: Demoted stat remains retrievable

- **WHEN** `close_rate` has been reclassified as detail
- **THEN** the value SHALL still be present in the payload and SHALL be retrievable on demand without a
  new server request

#### Scenario: Priority queue remains unfiltered

- **WHEN** any item is reclassified as detail
- **THEN** that item SHALL still appear, unfiltered, in `priority_queue`

### Requirement: Disclosure depth is capped at two levels

The surface SHALL expose at most two levels of progressive disclosure below the resting view. The
permitted path is resting surface, then focus card, then detail. No third level SHALL be introduced.

#### Scenario: Detail is reachable in two steps

- **WHEN** the operator requests the full relay statistics from the resting surface
- **THEN** the information SHALL be reachable within two disclosure steps

#### Scenario: A third nested level is rejected

- **WHEN** a panel would require the operator to open a third nested level to reach a value
- **THEN** that value SHALL instead be surfaced at the second level or omitted from the surface

### Requirement: Attention load is instrumented

The system SHALL record the count of items presented in the attention layer per render, and the rate at
which the operator acts on versus dismisses top-tier items, so that ranking quality is measurable rather
than assumed.

#### Scenario: Attention count is recorded

- **WHEN** the vault renders
- **THEN** the number of items occupying the attention layer SHALL be recorded

#### Scenario: Rubber-stamping is detectable

- **WHEN** the operator accepts top-tier items without ever overriding across a rolling window
- **THEN** the recorded override rate SHALL reflect that, so the ranking can be identified as
  uninformative
