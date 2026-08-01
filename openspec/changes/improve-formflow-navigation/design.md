## Context

`static/js/formflow.js` is a single-module panel (~1270 LOC) built on the same shell primitives as `notes.js`: `notes-pane` CSS, `Modals.register`/`Modals.minimize` for rail-chip lifecycle, `wireSwipeDismiss` for swipe-down-to-minimize, and a header with one `modal-minimize-btn`. Notes is a passive browsing surface, so minimize-only is fine there — there's nothing to lose by backgrounding it. FormFlow is a stateful wizard (`_questions`, `_answers`, `_currentIdx`, `_activeFlowId`, `_flowPhases` module-level vars) that can be entered two ways: manually opening the panel, or `openWithQuestions`/`openWithText` called from chat (`formflowFromChat.js`), which jumps straight past the input screen into `form`. There is currently no full-close affordance inside the panel itself and no Escape handling in `modalManager.js` or `formflow.js`.

## Goals / Non-Goals

**Goals:**
- Give the user an unambiguous, always-visible way to leave FormFlow from any screen (form/review/handoff), with Escape as a keyboard equivalent.
- Never silently discard answers the user has already entered — confirm or offer to keep them as a resumable draft.
- Let the user move through questions faster: skip optional ones, jump directly to any question, clear a single answer.
- Keep the change additive to `formflow.js`; don't touch the parse pipeline, decision-flow content, or handoff generation.

**Non-Goals:**
- Server-side persistence of drafts (localStorage only — this is a single-browser, single-session convenience, not cross-device sync).
- Changing what minimize does, or removing it — minimize/rail-chip restore stays as the "pause without deciding" path; Exit is a new, separate action for "I'm done / I want out."
- Reworking `Modals.register`/`modalManager.js` global behavior for all panels — Escape handling is scoped to FormFlow unless it turns out to be a two-line generalization (see Decisions).

## Decisions

**Exit is a distinct control from Minimize, not a repurposing of it.**
Minimize already has defined, relied-upon semantics (rail chip + `Modals.minimize`, restorable via `restoreFn`). Overloading it to also mean "close and discard" would make minimize unpredictable. Alternative considered: make the backdrop click do a full close instead of minimize — rejected because accidental backdrop clicks (e.g. missed a button on mobile) would then risk discarding answers; backdrop click stays mapped to `closePanel('down')` (minimize) for safety, and the new Exit button is the deliberate discard/close path.

**Confirm-before-discard only when there's something to lose.**
`_hasAnswer(q)` already exists per-question. Exit checks whether any visible question has an answer; if none, close immediately with no prompt (matches "no way to exit" complaint — for an empty/just-opened form, exit should be instant, not gated). If answers exist, show a small inline confirm (reuse `.ff-error`-style inline UI rather than a new modal-on-modal) with three actions: **Save draft & exit**, **Discard & exit**, **Cancel**. This avoids stacking a second overlay on top of the panel.

**Escape key: scoped listener on `_pane`, state-aware.**
Reuses the existing `_pane.addEventListener('keydown', ...)` block (currently only handles Enter). Behavior: if `document.activeElement` is a text input/textarea inside the pane, first Escape blurs it (standard browser expectation, avoids surprising exits while typing); a second Escape (focus no longer in a field) triggers the same Exit-with-confirm path as the button. Only active while `_screen` is `form`, `review`, or `handoff` — on the `input`/`loading` screens Escape is a no-op (nothing stateful to lose, and closing mid-parse would orphan the in-flight fetch stream reader, which already has its own error handling if the panel disappears). This stays local to `formflow.js`; no change to `modalManager.js` since no other panel currently needs Escape-to-close and speculatively generalizing it would violate the "keep scope additive" constraint from the proposal.

**Autosave to `localStorage`, keyed constant (single active draft).**
FormFlow supports exactly one open wizard at a time (module-level state, not per-instance), so a single fixed key (`formflow.draft.v1`) is sufficient — no need for per-flow or per-session keys. Written on every `_answers` mutation (already funneled through the `_build*` input handlers) via a small debounced writer, and cleared on: successful exit-with-discard, reaching the end of the handoff screen (flow completed), or explicit "Parse another form" restart. On `openPanel()`, if a draft exists and no in-memory `_questions` are already loaded, show a **Resume** choice on the input screen ("Resume previous form (N of M answered)" / "Start fresh") instead of auto-loading it — auto-loading would surprise a user who explicitly wanted to start a new paste.

**Skip vs Next stay visually distinct but reuse the same advance path.**
Skip only renders for `!q.required` questions, sits next to Next, and calls the same `_advanceForm()` used by Next — the only difference is it doesn't require `_hasAnswer(q)` to be enabled (Next already isn't blocked for optional questions, so Skip is mainly a clarity affordance: an explicit "I'm intentionally leaving this blank" action rather than the user wondering if Next silently skipped).

**Jump-to-question via existing phase pills + a lightweight outline, not a full step-list rewrite.**
`.ff-phase-pill` elements already render one per flow phase; making them clickable (jump to first visible question in that phase) is a small addition. For flows without phases (most pasted/uploaded forms), add a compact numbered outline strip above the question (reuses `.ff-q-number` row) that's clickable per-question when there are ≤ ~12 visible questions; beyond that, keep it text-only to avoid clutter (matches the existing minimalist input styling rather than introducing a new sidebar/list component).

## Risks / Trade-offs

- **[Risk] localStorage draft goes stale** (old question set from a since-edited paste) → **Mitigation**: store a content hash or the raw source alongside the draft; on resume, only offer it if the underlying question IDs still make sense to the user (show the first question's label in the resume prompt so they can recognize/reject it).
- **[Risk] Escape-blurs-first-then-exits could feel like two presses are needed even when not typing** → **Mitigation**: only intercept the first Escape for blur when `document.activeElement` is actually inside `_pane` and is an input/textarea; otherwise Escape exits immediately.
- **[Risk] Confirm-inline UI adds a new screen-state edge case** (user hits Exit, sees confirm, then also hits Escape or clicks minimize while confirm is showing) → **Mitigation**: treat the confirm as a small overlay flag (`_exitConfirmShowing`) checked first in the Escape handler and in the minimize handler, so any of those inputs collapse to the same three choices rather than opening a second confirm or bypassing it.

## Migration Plan

Purely additive UI change behind existing module-level state; no data migration. Ship in one pass since it's a single file's UX shell (per repo convention, phased execution applies to changes touching >5 files — this touches essentially one). Rollback is a plain revert of `formflow.js` (and `modalManager.js` only if that generalization ends up used, which is not planned).

## Open Questions

- Should "Save draft & exit" also be reachable from the minimize action (i.e., does minimizing mid-form implicitly autosave), or is autosave already unconditional on every keystroke regardless of how the user leaves? Leaning toward: autosave is unconditional (already covers this), so minimize needs no special-casing — only Exit needs the confirm because Exit is the only path that can *discard*.
