## 1. Exit affordance + confirm

- [x] 1.1 Add an exit button (distinct from `ff-minimize-btn`) to the pane header, visible/enabled only while `_screen` is `form`, `review`, or `handoff`
- [x] 1.2 Implement `_hasAnyAnswer()` helper (any visible question with `_hasAnswer(q)` true) to decide immediate close vs confirm
- [x] 1.3 Build the inline exit-confirm UI (Save draft & exit / Discard & exit / Cancel) rendered within the pane, gated by an `_exitConfirmShowing` flag
- [x] 1.4 Wire "Discard & exit" to clear in-memory state and call `_forceClose()`; wire "Save draft & exit" to persist the draft (depends on 3.1) then `_forceClose()`; wire "Cancel" to hide the confirm and return to the prior screen unchanged

## 2. Escape key wiring

- [x] 2.1 Extend the existing `_pane.addEventListener('keydown', ...)` handler: on `Escape`, if `_screen` is `input` or `loading`, no-op
- [x] 2.2 On `Escape` with `_screen` in `form`/`review`/`handoff`: if `document.activeElement` is a text input/textarea inside `_pane`, blur it and stop; otherwise trigger the same path as the exit button (1.2–1.4)
- [x] 2.3 If `_exitConfirmShowing` is true, make Escape resolve to "Cancel" (dismiss confirm) rather than re-triggering exit

## 3. Autosave / resume draft

- [x] 3.1 Add `_saveDraft()` writing `{questions, answers, currentIdx, activeFlowId, flowPhases}` to `localStorage['formflow.draft.v1']`, called from the existing answer-mutation call sites (`_buildText`, `_buildTextarea`, `_buildChoice`, `_buildMulti`, `_buildYesNo`, `_buildScale`) and on question navigation
- [x] 3.2 Add `_loadDraft()` / `_clearDraft()` helpers with basic shape validation (ignore corrupt/old-shape entries)
- [x] 3.3 On `openPanel()`, if a draft exists and `_questions` is empty, render a "Resume previous form (N of M answered)" choice on the input screen alongside the normal paste/upload UI, using the draft's first question label so the user can recognize it
- [x] 3.4 Wire resume choice to restore `_questions`/`_answers`/`_currentIdx`/`_activeFlowId`/`_flowPhases` and jump to the form screen; wire "start fresh" to clear the draft and show the normal input screen
- [x] 3.5 Clear the draft on: discard-and-exit (1.4), reaching end of handoff screen, and `_restart()`

## 4. Skip, jump-to-question, per-question clear

- [x] 4.1 Add a Skip control next to Next in `_updateNav`, shown only when `!q.required`; clicking calls `_advanceForm()` without requiring `_hasAnswer(q)`
- [x] 4.2 Make `.ff-phase-pill` elements clickable in `_renderPhases`: clicking a non-active pill navigates to the first visible question in that phase
- [x] 4.3 Add a compact clickable question outline (reuse `.ff-q-number` styling) shown when `_visibleQs().length` is small enough (≈≤12); clicking an entry navigates directly via `_renderQuestion(index)`
- [x] 4.4 Add a Clear control near the question input that resets `_answers[q.id]` and re-renders the current question's input to its empty state

## 5. Verify

- [ ] 5.1 Manual smoke-check: paste a list of questions, confirm Exit closes instantly with no answers entered
- [ ] 5.2 Manual smoke-check: answer a question, hit Exit, confirm the Save draft / Discard / Cancel choices each behave as specified
- [ ] 5.3 Manual smoke-check: Escape blurs an active textarea first, then exits on second press; Escape on input/loading screen is a no-op
- [ ] 5.4 Manual smoke-check: answer a few questions, close the tab/reload, reopen FormFlow, confirm the resume prompt appears and restores state correctly
- [ ] 5.5 Manual smoke-check: Skip an optional question, jump via phase pill and via question outline, clear a single answer — confirm state stays consistent through review and handoff screens
- [ ] 5.6 Confirm chat-triggered entry (`sendMessageToFormFlow` → `openWithQuestions`/`openWithText`) still opens correctly and the new exit/Escape controls work identically when entered this way
