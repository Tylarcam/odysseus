## Why

FormFlow (`static/js/formflow.js`) lets an operator paste or upload a form/questionnaire and step through it one question at a time. Once the form screen is showing, the panel header only has a **minimize** button — the same affordance `notes.js` uses for a passive browsing pane. Minimize just backgrounds FormFlow into a rail chip; it doesn't close it, and there's no Escape-key handling or explicit exit/cancel control anywhere in the flow. A user who pastes a series of questions (directly, or via `sendMessageToFormFlow` from chat, which auto-opens straight to the form screen) has no discoverable way to bail out mid-wizard. This is worse than a passive pane because the user is now inside a stateful, multi-step flow they may want to abandon or pause, and any answers typed so far are silently lost the moment they do find a way out (toggling the same rail/sidebar button that opened it).

## What Changes

- Add an explicit **Exit** control on the form/review/handoff screens, separate from Minimize, that fully closes FormFlow. If there are unsaved answers, show a lightweight confirm ("Discard N answers?" / "Save draft & exit" / "Cancel") instead of silently discarding.
- Wire the **Escape** key to trigger the same exit-with-confirm behavior while the form/review/handoff screens are active, ignored while a text input/textarea has focus with unsaved keystrokes pending (first Escape blurs the field; second exits) to avoid stomping accidental presses.
- **Autosave** in-progress state (questions, answers, currentIdx, activeFlowId, flowPhases) to `localStorage` on every change, and offer **Resume where you left off** the next time FormFlow is opened while a draft exists, instead of always starting blank.
- Add a **Skip** control for non-required questions, distinct from Next (Next is disabled until an answer is given for required questions; Skip explicitly moves on without one).
- Make the phase pills (`.ff-phase-pill`) and a compact question outline **click-to-jump**, so an operator can jump directly to any earlier (or already-visible) question instead of stepping Back one at a time.
- Add a per-question **Clear** control to blank out the current answer without retyping.

## Capabilities

### New Capabilities
- `formflow-navigation`: Exit/cancel affordance and confirm-before-discard behavior, Escape-key handling, autosave and resume-draft behavior, skip/jump/clear controls for moving through a FormFlow question stack.

### Modified Capabilities
- (none — `openspec/specs/` has no existing FormFlow capability spec to modify; this is the first spec coverage for FormFlow's in-form navigation shell)

## Impact

- `static/js/formflow.js` — primary: header exit button, confirm dialog, Escape listener, autosave/restore, skip/clear controls, phase-pill/outline jump handlers
- `static/js/modalManager.js` — only if Escape-to-close is generalized for reuse by other panels; otherwise scoped locally to formflow.js
- `static/js/panelSheet.js` — no functional change expected; confirms swipe-down still maps to minimize, not full exit
- Out of scope: `formflowFromChat.js` (chat parsing), `formflowFlows.js` (built-in decision-flow content), `formflowHandoffs.js` (handoff generation), `routes/formflow_routes.py` (parse API) — none of these need to change for this proposal
- Tests: no existing JS test harness covers `formflow.js`; verification will be a manual smoke-check (open FormFlow, paste questions, confirm exit/resume/skip/jump behavior), matching the pattern used in `vault-directive-triage-modal`
