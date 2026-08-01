## ADDED Requirements

### Requirement: Explicit exit control
FormFlow SHALL provide an exit control, distinct from the minimize control, that is visible on the form, review, and handoff screens and that fully closes the FormFlow panel (unregisters it, rather than backgrounding it as a rail chip).

#### Scenario: Exit with no answers entered
- **WHEN** the user activates the exit control while on the form screen and no visible question currently has an answer
- **THEN** FormFlow closes immediately with no confirmation prompt

#### Scenario: Exit with unsaved answers
- **WHEN** the user activates the exit control while at least one visible question has an answer
- **THEN** FormFlow shows an inline confirm offering "Save draft & exit", "Discard & exit", and "Cancel", and takes no closing action until the user chooses one

#### Scenario: Cancel the exit confirm
- **WHEN** the user chooses "Cancel" from the exit confirm
- **THEN** FormFlow returns to the screen and question the user was on, with all answers intact

### Requirement: Escape key closes the active form
While the form, review, or handoff screen is active, the Escape key SHALL trigger the same exit behavior as the exit control, except that if a text input or textarea inside the panel has focus, the first Escape press blurs that field instead of exiting.

#### Scenario: Escape while typing in a question field
- **WHEN** the user presses Escape while focus is inside a text input or textarea on the form screen
- **THEN** the field loses focus and FormFlow does not close

#### Scenario: Escape with no field focused
- **WHEN** the user presses Escape while no input or textarea inside the panel has focus, and the form/review/handoff screen is active
- **THEN** FormFlow applies the same exit behavior as the exit control (immediate close if no answers, confirm if answers exist)

#### Scenario: Escape on the input or loading screen
- **WHEN** the user presses Escape while the input screen or loading screen is active
- **THEN** FormFlow takes no action

### Requirement: Autosave and resume draft
FormFlow SHALL persist in-progress question/answer state to local storage as answers change, and SHALL offer to resume that draft the next time the panel is opened with no form already loaded in memory.

#### Scenario: Draft persisted while answering
- **WHEN** the user enters or changes an answer to any question
- **THEN** the current questions, answers, current question index, and active flow identifier are saved to local storage

#### Scenario: Resume offered on reopen
- **WHEN** the user opens FormFlow and a saved draft exists and no questions are currently loaded in memory
- **THEN** the input screen offers a "Resume previous form" choice showing how many questions were answered, alongside the option to start fresh

#### Scenario: Draft cleared after discard or completion
- **WHEN** the user discards the current form via the exit confirm, or reaches the end of the handoff screen, or explicitly restarts via "Parse another form"
- **THEN** the saved draft is removed from local storage

### Requirement: Skip control for optional questions
FormFlow SHALL show a Skip control, separate from Next, on any question that is not required, allowing the user to advance without providing an answer.

#### Scenario: Skip an optional question
- **WHEN** the current question is not required and has no answer
- **THEN** a Skip control is visible, and activating it advances to the next visible question without requiring an answer

#### Scenario: No skip control on required questions
- **WHEN** the current question is required
- **THEN** no Skip control is shown

### Requirement: Jump to any visible question
FormFlow SHALL let the user navigate directly to any already-reachable question instead of only stepping one at a time via Back/Next.

#### Scenario: Jump via phase pill
- **WHEN** the active flow has phases and the user activates a phase pill other than the current one
- **THEN** FormFlow navigates to the first visible question in that phase

#### Scenario: Jump via question outline
- **WHEN** the visible question count is small enough that a per-question outline is shown and the user activates an entry in it
- **THEN** FormFlow navigates directly to that question, preserving any answers already entered on other questions

### Requirement: Clear a single answer
FormFlow SHALL let the user clear the answer to the currently displayed question without needing to manually erase text or reselect options.

#### Scenario: Clear a text or choice answer
- **WHEN** the current question has an existing answer and the user activates the clear control for it
- **THEN** the answer for that question is removed and the question's input control returns to its empty/unselected state
