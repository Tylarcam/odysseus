## ADDED Requirements

### Requirement: Voice carries intent and verdict; the screen carries state and exact values

Spoken output SHALL carry the consequence, the deadline, the recommended action, and its uncertainty.
Spoken output SHALL NOT enumerate lists, nor carry values whose precision matters — names, dates,
identifiers, URLs, and amounts SHALL be rendered on screen.

#### Scenario: Consequence is spoken, count is not

- **WHEN** a relay handoff has failed and blocks downstream work
- **THEN** the spoken line SHALL state the consequence and its time sensitivity, and SHALL NOT be a bare
  count such as "one failed"

#### Scenario: Exact values are shown, not spoken

- **WHEN** a proposed action involves a specific recipient, date, and amount
- **THEN** those values SHALL be rendered on screen, and the spoken line SHALL refer to them without
  requiring the operator to retain them by ear

#### Scenario: Long option sets are not read aloud

- **WHEN** more than two options are available
- **THEN** the options SHALL be rendered on screen rather than enumerated in speech

### Requirement: Spoken turns are capped at two sentences

A single spoken turn SHALL NOT exceed two sentences. Content exceeding that budget SHALL be rendered on
screen instead of spoken, or summarized to fit.

#### Scenario: A long brief is summarized rather than read

- **WHEN** the available narration for a turn would exceed two sentences
- **THEN** the spoken output SHALL be reduced to at most two sentences and the remainder SHALL be
  available on screen

#### Scenario: Screen presence shortens rather than lengthens speech

- **WHEN** the corresponding detail is already visible on screen
- **THEN** the spoken line SHALL be shortened rather than restating the visible detail

### Requirement: A status word is emitted before substantive speech

The system SHALL emit a single status word indicating its current activity as soon as processing begins
and before the first substantive sentence, so the operator is never left in silence uncertain whether
input was received.

#### Scenario: Status word precedes a slow response

- **WHEN** the agent begins processing a spoken command
- **THEN** a status word such as `recalling`, `inferencing`, `clarifying`, or `correcting` SHALL be
  emitted before the first substantive sentence

#### Scenario: Operator receives acknowledgement of being heard

- **WHEN** a spoken command has been captured
- **THEN** an acknowledgement SHALL be presented before any substantive response

### Requirement: Verification text is rendered before any external mutation

Before performing an action with effects outside the vault, the system SHALL render what it heard and
the interpreted action it is about to take, and SHALL require confirmation.

#### Scenario: Interpreted command is shown before sending

- **WHEN** a spoken command would send an email
- **THEN** the interpreted recipient, subject, and timing SHALL be rendered and confirmation SHALL be
  required before sending

#### Scenario: Misrecognition is correctable before it takes effect

- **WHEN** the rendered interpretation does not match the operator's intent
- **THEN** the operator SHALL be able to correct or cancel it before the action is performed

#### Scenario: Read-only actions do not require confirmation

- **WHEN** a spoken command only retrieves or focuses information
- **THEN** confirmation SHALL NOT be required

### Requirement: Verbatim narration is not rendered as a scrolling transcript by default

The surface SHALL NOT display a running verbatim duplicate of spoken output by default. Captions SHALL be
available behind an explicit operator-controlled toggle.

#### Scenario: No transcript by default

- **WHEN** the agent speaks and no caption preference has been set
- **THEN** the spoken words SHALL NOT be duplicated as on-screen running text

#### Scenario: Captions available on request

- **WHEN** the operator enables captions
- **THEN** spoken output SHALL be accompanied by synchronized text

### Requirement: Every voice affordance has a keyboard equivalent

Every action reachable by voice SHALL be reachable without voice. No capability SHALL be voice-only.

#### Scenario: Voice-armed action is also keyboard-reachable

- **WHEN** an action can be triggered by a spoken command
- **THEN** the same action SHALL be reachable via keyboard or pointer

#### Scenario: Recovery does not require speech

- **WHEN** speech recognition is unavailable or repeatedly failing
- **THEN** the operator SHALL be able to complete the intended action through a non-voice path

### Requirement: Reported voice state reflects actual voice state

The voice status presented on the surface SHALL be derived from the live state of the voice subsystem and
SHALL NOT be a fixed value.

#### Scenario: Idle voice reports standby

- **WHEN** no voice session is active
- **THEN** the reported voice state SHALL indicate standby

#### Scenario: Active voice reports listening

- **WHEN** a voice session is capturing input
- **THEN** the reported voice state SHALL indicate that it is listening, rather than standby
