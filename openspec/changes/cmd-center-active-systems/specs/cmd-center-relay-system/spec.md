## ADDED Requirements

### Requirement: Handoffs display lineage to their originating object
A handoff row in RELAY SHALL show its `related_to` parent (job or note) when a lineage edge exists (per `cmd-center-lineage`), so the operator can see why a given handoff exists without cross-referencing AGENCY/PROD manually.

#### Scenario: Handoff from a job shows its source
- **WHEN** a handoff was materialized from a job
- **THEN** its RELAY row SHALL display a reference back to that job

### Requirement: Claimed-but-stuck handoffs are distinguished from needs-attention
A handoff whose `handoff_relay_status` is `running` (claimed) for longer than the configured stuck-hours threshold with no transition to `complete`/`failed` SHALL be flagged `stalled: {reason: "claimed_stuck"}` (per `cmd-center-stalled-item-detection`), rendered distinctly from the existing `needs_attention` bucket rather than merged into it.

#### Scenario: Claimed handoff never completes
- **WHEN** a handoff has been `running` for longer than the stuck-hours threshold
- **THEN** RELAY SHALL show it in a distinct "stuck" grouping, separate from unclaimed `needs_attention` handoffs

### Requirement: Relay stats include an outcome/close-rate view
`relay_stats` SHALL report, over a rolling window, how many handoffs issued were completed vs. failed vs. still open, so the operator can see how much of what's delegated actually returns.

#### Scenario: Weekly close rate is shown
- **WHEN** 10 handoffs were issued this week and 7 completed
- **THEN** `relay_stats` SHALL report a 70% close rate alongside the raw counts
