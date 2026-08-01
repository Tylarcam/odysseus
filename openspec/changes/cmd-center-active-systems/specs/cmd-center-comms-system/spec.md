## ADDED Requirements

### Requirement: Reminder notes carry lineage back to the urgent email that spawned them
`action_check_email_urgency` SHALL record a lineage edge (per `cmd-center-lineage`) from the email (`account_id:uid`) to the reminder note it creates, so MEM/PROD can display "this came from an email" instead of an unexplained note.

#### Scenario: Reminder note shows its email origin
- **WHEN** an urgent email causes a reminder note to be created
- **THEN** that note's `related_to` SHALL include `{kind: "email", id: "<account_id>:<uid>"}`

### Requirement: Comms focus tracks a closed-loop conversion rate
`comms_focus` SHALL report how many urgent emails were converted into directives (reminder notes) over a rolling window (e.g. the current week), computed from lineage edges of `relation="reminded"`.

#### Scenario: Weekly conversion count is shown
- **WHEN** 3 urgent emails were converted into reminder notes this week
- **THEN** `comms_focus` SHALL display that count

### Requirement: Unread urgent email escalates via the stalled-item detector
An email flagged urgent by `action_check_email_urgency` that remains unread for longer than 48 hours SHALL be flagged stalled (per `cmd-center-stalled-item-detection`) and surfaced with elevated urgency in `priority_queue`.

#### Scenario: Urgent email ignored past 48 hours
- **WHEN** an email scored urgent has remained unread for more than 48 hours
- **THEN** it SHALL appear in `priority_queue` at escalated urgency, not only in the COMMS inbox list
