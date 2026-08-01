## ADDED Requirements

### Requirement: Holding Space arms voice delegate
While the vault is open and no other surface owns keyboard focus (see the focus-scoping requirement below), holding the `Space` key for at least 3000ms SHALL trigger the same voice-delegate activation as clicking the Audio I/O panel (`_activateVoiceDelegate()`).

#### Scenario: Hold past threshold arms voice
- **WHEN** the vault is open, no modal is active, focus is not in a text input, and the operator holds `Space` for 3000ms or longer
- **THEN** voice delegate activation fires exactly once, identically to clicking the Audio panel

#### Scenario: Releasing early does not arm voice
- **WHEN** the operator presses and releases `Space` after only 1000ms
- **THEN** voice delegate activation does not fire

#### Scenario: Space does not double-fire on key repeat
- **WHEN** the operator holds `Space` for 6000ms (well past the 3000ms threshold)
- **THEN** voice delegate activation fires exactly once, not once per repeated `keydown` event

### Requirement: Escape dismisses the vault
While the vault is open and no other surface owns keyboard focus, pressing `Escape` SHALL trigger the same minimize/dismiss behavior as clicking `#cmd-center-minimize`.

#### Scenario: Esc minimizes the open vault
- **WHEN** the vault is open, no modal is active, and the operator presses `Escape`
- **THEN** the vault minimizes via the same code path as the minimize button click

### Requirement: Focus-owning surfaces suppress global Space/Esc handling
Global `Space`-hold and `Escape` handling SHALL be suppressed whenever: the active element is a text input, textarea, or contenteditable element; the Directive Triage modal is open (`isDirectiveTriageOpen()` returns true); or any element sets a `data-cmd-modal-open` marker on `<body>` indicating another modal claims input focus.

#### Scenario: Typing a space in a note does not arm voice
- **WHEN** focus is inside a text input (e.g. editing a note title) and the operator holds `Space`
- **THEN** voice delegate activation does not fire and the space character is entered normally

#### Scenario: Esc inside Directive Triage closes the triage modal, not the vault
- **WHEN** the Directive Triage modal is open and the operator presses `Escape`
- **THEN** only the triage modal's own Escape handler runs (closing the modal); the vault-level minimize handler does not also fire

#### Scenario: Any modal can claim focus via the marker attribute
- **WHEN** a modal other than Directive Triage sets `data-cmd-modal-open="true"` on `<body>` while open
- **THEN** global Space-hold and Escape handling are suppressed until the marker is cleared

### Requirement: Audio hint text matches implemented behavior
The `audio.hint` string returned by `build_cmd_center` SHALL only describe keyboard shortcuts that are implemented and functional. If a described shortcut is not implemented, the hint text SHALL be updated to remove the claim rather than leaving stale copy in place.

#### Scenario: Hint text is accurate after this change ships
- **WHEN** `audio.hint` is rendered in the Audio I/O panel
- **THEN** every shortcut it mentions (Space-hold, Esc) is a real, working global handler as specified above
