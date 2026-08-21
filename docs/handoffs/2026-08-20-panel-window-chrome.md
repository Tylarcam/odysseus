# Handoff: Panel window chrome parity (close X + maximize)

Validated 2026-08-20 against the Odysseus repo. Do **not** re-litigate the decisions below. Implement as written. Stop after each phase for approval.

---

## Validation verdict

User observation: Notes (`#notes-pane`) has minimize + maximize, no X. Documents (`#doclib-modal`) has X (`#doclib-close.close-btn`) + injected `_`, no maximize button.

| Claim | Status | Evidence |
|---|---|---|
| Notes has `#notes-fullscreen-toggle` (square) and `#notes-minimize-btn` (`_`), no close X | **Confirmed** | `static/js/notes.js` ~1208–1210. Minimize calls `closePanel('down')` (~1274–1278). Full close is `closePanel()` with no arg (~1762–1767). |
| Documents has `#doclib-close.close-btn` with `✖` | **Confirmed** | `static/js/documentLibrary.js` ~1921, wired ~2151. |
| Documents lacks a maximize button | **Confirmed** | Header HTML is title + close only. `_` comes from `modalManager.injectMinimizeButton`. |
| Documents already has enter/exit fullscreen callbacks | **Confirmed, but disabled** | `documentLibrary.js` ~2102–2142. Comment: top-edge snap “breaks dense icon/tool rows”. `enableFullscreen: false`. Existing `enterFullscreen` paints `100vw`/`100vh` and **covers the sidebar**. Do not turn that flag on. |
| Shared drag helper is `makeWindowDraggable` | **Confirmed** | `static/js/windowDrag.js`. Fullscreen snap only runs when `onEnterFullscreen` is supplied **and** `enableFullscreen !== false`. |
| Minimize `_` is auto-injected | **Confirmed** | `modalManager.js` `injectMinimizeButton` ~1348–1393. Inserts `_` before `.close-btn, .modal-close`. Scans `_AUTO_WIRE` ids every 1s. |
| Calendar / tasks / gallery / agent-bin / cookbook / settings call `makeWindowDraggable` without `onEnterFullscreen` | **Confirmed** | Calendar even comments “doesn't support fullscreen snap” (`calendar.js` ~656–662). Cookbook same (`cookbook.js` ~2204–2222). |
| Tile manager already maximize-snaps `.modal-header` drags | **Confirmed** | `tileManager.js` `_zoneForPointer`: near top → `{ name: 'maximize' }` beside rail; `y <= 0` → true fullscreen covering sidebar. `_unsnap` restores pre-snap. **Not exported.** |
| Split-chat already has `_` + X + custom `fsClass` | **Confirmed** | `splitChat.js` ~61–100. |
| FormFlow / Story Canvas are Notes-style panes: `_`, no X, no maximize button | **Confirmed** | `formflow.js` ~360–365; `storyCanvas.js` ~109–111. |
| Research overlay has `_` + X, uses `themeModule.makeDraggable` (wraps `makeWindowDraggable`) | **Confirmed** | `research/panel.js` ~360–364, ~293–294. |
| CMD Center / Vault is already a full workspace | **Confirmed** | No `makeWindowDraggable`. Minimize only (`cmdCenter.js` ~3612). **Out of scope.** |
| `data-fs-btn-obs` on Notes | **Confirmed** | Notes MutationObserver syncing the FS icon (`notes.js` ~227–231). Attribute is `data-fs-btn-obs`. |

**Corrections to the original ask**

1. Do **not** copy Notes’ maximize markup into every panel. Inject once from `makeWindowDraggable`.
2. Do **not** set Documents `enableFullscreen: true`. That callback covers the sidebar (`100vw`). The square button must use tileManager **maximize** (safe rect beside the rail), matching Notes’ `_enterNotesFullscreen` / `_notesFullscreenSafeRect`.
3. “All other panels” ≠ nested dialogs (calendar settings, assistant settings, PDF export, skill markdown, gallery inpaint, cmd-vis). Those stay as they are.
4. Notes minimize already exists. The new X is a **full close** (`closePanel()`), not a second minimize.

---

## Decisions (non-negotiable)

| Decision | Choice | Why |
|---|---|---|
| Chrome order, right cluster | `_` then square maximize then `✖` | Native window chrome. Documents already ends with X. Notes already has `_` then square; append X after square. |
| Maximize implementation | Export `getMaximizeZone` / `unsnapModal` / `toggleMaximize` from `tileManager.js`; inject button in `windowDrag.js` | Avoid 12 copy-pasted enter/exit callbacks. Tile manager already owns maximize geometry. |
| When the injected button uses custom FS callbacks | Only if `enableFullscreen === true` **and** `onEnterFullscreen` is provided (split-chat, email, Notes own button skipped) | Documents has callbacks but `enableFullscreen: false` — button must **not** use the 100vw path. |
| Notes X markup | Imitate Documents: `<button class="close-btn" id="notes-close" aria-label="Close notes">✖</button>` | User pointed at `#doclib-close`. |
| Notes X behavior | `closePanel()` with **no** argument | `direction === 'down'` minimizes to chip. Empty call is full close (`notes.js` ~1762). |
| FormFlow / Story Canvas X | Same `close-btn` pattern; call `closePanel()` / `closeStoryCanvas()` with no arg | They already treat `'down'` as minimize, matching Notes. |
| CMD Center / Vault | **Do not touch** | Already fills the workspace; X would fight the vault. |
| Nested / satellite dialogs | **Do not touch** | Not tool windows. |
| Document **editor** pane | **Do not touch** | Has its own chevron fullscreen in `document.js`. |
| `sessions.js` fallback `#library-modal` | **Do not touch** | Dead path when `documentModule.openLibrary` exists (~2671–2674). Live UI is `documentLibrary.js`. |
| Mobile | Hide `.modal-fullscreen-btn` / `[data-fullscreen-toggle]` at `max-width: 768px` and in `.notes-mobile-mode` | Notes already hides `#notes-fullscreen-toggle`. Sheets are already full-viewport. Keep X visible (Documents does). |
| CSS class for the square | `modal-minimize-btn modal-fullscreen-btn` + `data-fullscreen-toggle="1"` | Reuse existing 24×24 bordered square. Do **not** invent a third header-button skin. |
| Minimize insert vs FS insert race | `injectMinimizeButton` inserts **before** `.modal-fullscreen-btn` if present, else before close. FS insert goes **after** existing `.modal-minimize-btn` if present, else before close. | 1s scan can run before or after `makeWindowDraggable`. Either order must land `_` · square · X. |
| New dependencies | None | Vanilla JS. |
| Phasing | ≤5 files per phase; stop for approval | Repo CLAUDE.md / AGENTS.md. |

---

## Diagram

```
  USER clicks header chrome
           |
           +-- [_]  --> existing minimize (modalManager / notes closePanel('down'))
           |
           +-- [square] --> [EDIT 2] windowDrag.ensureFullscreenToggle
           |                    |
           |                    +-- custom FS path (enableFullscreen && onEnterFullscreen)
           |                    |     split-chat / email
           |                    +-- default path --> [EDIT 1] tileManager.toggleMaximize
           |                                              getMaximizeZone()  (beside rail)
           |                                              or unsnapModal()
           |
           +-- [✖]  --> .close-btn
                          Documents: already #doclib-close
                          Notes:     [EDIT 4] #notes-close --> closePanel()
                          FormFlow:  [EDIT 6] #ff-close
                          Story:     [EDIT 7] #sc-close

  [EDIT 3] modalManager.injectMinimizeButton  -- insert-before target includes FS btn
  [EDIT 5] style.css                          -- hide FS btn on mobile

  UNCHANGED: cmdCenter.js, document.js editor, nested dialogs, sessions.js fallback library
```

---

## The handoff prompt

Copy everything between the `BEGIN PROMPT` / `END PROMPT` markers into the builder.

````
BEGIN PROMPT

You are implementing a validated spec. Do not redesign. Do not re-litigate. Follow repo CLAUDE.md / AGENTS.md: ≤5 files per phase, stop for approval after each phase, no new dependencies.

This repo has NO `tsc` and NO eslint in package.json. Do not claim typecheck/lint passed. Verify with `node --check` on each edited `.js` file and the grep checks listed per phase.

GOAL
Give every desktop tool window the same header chrome cluster, right-aligned:

  [_] minimize   [square] maximize   [✖] close

Today:
- Notes (`static/js/notes.js` ~1208–1210) has `_` + square, no X. `#notes-minimize-btn` calls `closePanel('down')` (minimize to dock chip). Full close is `closePanel()` with no args (~1762–1767).
- Documents (`static/js/documentLibrary.js` ~1921) has `#doclib-close.close-btn` (`✖`). `_` is injected by `modalManager.injectMinimizeButton`. No maximize button. Do NOT set `enableFullscreen: true` — existing `enterFullscreen` (~2103–2118) covers the sidebar with 100vw/100vh. The square button must use tileManager **maximize** (safe rect beside the rail).
- Split-chat and email already have custom `onEnterFullscreen` with `enableFullscreen` default true. Their injected/existing square should keep using those callbacks.
- FormFlow and Story Canvas are Notes-style panes: `_`, no X.
- CMD Center / nested dialogs / document editor pane / `sessions.js` `#library-modal` fallback: do not touch.

================================================================
PHASE 1 — shared maximize API + inject button + minimize insert order
Files (3): static/js/tileManager.js, static/js/windowDrag.js, static/js/modalManager.js
================================================================

1) static/js/tileManager.js

`_unsnap` (~217) and `_viewportSafeRect` (~81) and `_applySnap` exist but are not exported. `snapModalToZone` (~378) refuses settings-modal unless zone.name === 'right-half' — the header button must bypass that.

Add these exports immediately after `export function snapModalToZone` (~378–384). Do not rename existing functions.

```js
export function getMaximizeZone() {
  const safe = _viewportSafeRect();
  return {
    name: 'maximize',
    rect: {
      left: safe.left,
      top: safe.top,
      width: safe.right - safe.left,
      height: safe.bottom - safe.top,
    },
  };
}

export function unsnapModal(modalOrContent) {
  if (!modalOrContent) return;
  const content = modalOrContent.querySelector
    ? (modalOrContent.querySelector('.modal-content, .research-pane') || modalOrContent)
    : modalOrContent;
  _unsnap(content);
}

export function isTileMaximized(modalOrContent) {
  if (!modalOrContent) return false;
  const content = modalOrContent.querySelector
    ? (modalOrContent.querySelector('.modal-content, .research-pane') || modalOrContent)
    : modalOrContent;
  const zone = content.dataset && content.dataset._tileZone;
  return zone === 'maximize' || zone === 'fullscreen';
}

/** Header-button maximize. Uses the rail-safe maximize zone, not y<=0 true fullscreen. */
export function toggleMaximize(modalOrContent) {
  if (typeof window !== 'undefined' && window.innerWidth <= 768) return;
  if (!modalOrContent) return;
  const content = modalOrContent.querySelector
    ? (modalOrContent.querySelector('.modal-content, .research-pane') || modalOrContent)
    : modalOrContent;
  if (isTileMaximized(content)) unsnapModal(content);
  else _applySnap(content, getMaximizeZone().rect, 'maximize');
}
```

2) static/js/windowDrag.js

At top, add:

```js
import { toggleMaximize, isTileMaximized } from './tileManager.js';
```

`tileManager.js` does **not** import `windowDrag.js`. Do not create a cycle.

Copy these icon constants from `notes.js` ~169–170 (keep them in windowDrag; do not import from notes.js):

```js
const FS_ICON_ENTER = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>';
const FS_ICON_EXIT = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M4 16V6a2 2 0 0 1 2-2h10"/></svg>';
```

Add `ensureFullscreenToggle(header, { modal, content, fsClass, enableFullscreen, onEnterFullscreen, onExitFullscreen })` in this file.

Skip inject if `header.querySelector('[data-fullscreen-toggle], #notes-fullscreen-toggle, .modal-fullscreen-btn')`.

Button:

```js
const btn = document.createElement('button');
btn.type = 'button';
btn.className = 'modal-minimize-btn modal-fullscreen-btn';
btn.dataset.fullscreenToggle = '1';
btn.title = 'Full screen';
btn.setAttribute('aria-label', 'Full screen');
btn.setAttribute('aria-pressed', 'false');
btn.innerHTML = FS_ICON_ENTER;
```

Insert:
- if `header.querySelector('.modal-minimize-btn:not(.modal-fullscreen-btn)')` exists, `insertBefore(btn, minBtn.nextSibling)` — if nextSibling is null, `appendChild`.
- else if `.close-btn, .modal-close, .modal-close-btn` exists, `insertBefore(btn, closeBtn)`.
- else `header.appendChild(btn)`.

`isCustomFs = enableFullscreen && typeof onEnterFullscreen === 'function'`.

Click (stopPropagation, preventDefault):
- if `window.innerWidth <= 768` return
- if `isCustomFs`: if `fsClass && modal.classList.contains(fsClass)` then `onExitFullscreen?.(cx, cy)` with no coords needed (call with no args if that's what callers use); else `onEnterFullscreen()`.
- else `toggleMaximize(content || modal)`.

Sync icon function:
- on = custom ? `fsClass && modal.classList.contains(fsClass)` : `isTileMaximized(content || modal)`
- title / aria-label / aria-pressed / innerHTML like `notes.js` `_syncNotesFullscreenBtn` (~176–185)

Observe `modal` (fallback `content`) class + `content` attributes `data-_tile-zone` with MutationObserver; set `header.dataset.fsBtnObs = '1'` to avoid double observers.

Call `ensureFullscreenToggle(header, { modal, content, fsClass, enableFullscreen, onEnterFullscreen, onExitFullscreen })` from `makeWindowDraggable` **after** resize/dock setup, once `header` is known (~72). Do **not** gate the inject on `enableFullscreen`. Every `makeWindowDraggable` header gets the square unless it already has one.

3) static/js/modalManager.js — `injectMinimizeButton` (~1348)

Change the insert-before target so `_` lands left of the square when the square already exists.

Replace the closeBtn lookup + insert (the block that currently does `header.querySelector('.close-btn, .modal-close')` and `insertBefore(btn, closeBtn)`) with:

```js
  const fsBtn = header.querySelector('.modal-fullscreen-btn, [data-fullscreen-toggle]');
  const closeBtn = header.querySelector('.close-btn, .modal-close, .modal-close-btn');
  const before = fsBtn || closeBtn;
  // ... create btn as today ...
  if (before && before.parentNode) before.parentNode.insertBefore(btn, before);
  else header.appendChild(btn);
```

Keep the existing “already has `.modal-minimize-btn`” early-return. Notes header already has `#notes-minimize-btn.modal-minimize-btn`, so Notes will not get a second `_`. **Caveat:** Notes also has `#notes-fullscreen-toggle.modal-minimize-btn`, so the early-return `.modal-minimize-btn` match still fires. That is correct — do not inject a second `_` into Notes.

PHASE 1 VERIFY (run all)
- `node --check static/js/tileManager.js`
- `node --check static/js/windowDrag.js`
- `node --check static/js/modalManager.js`
- Grep: `export function toggleMaximize` exists in tileManager.js
- Grep: `ensureFullscreenToggle` or `data-fullscreen-toggle` exists in windowDrag.js
- Grep: `injectMinimizeButton` insert uses `fsBtn` / `modal-fullscreen-btn`
- Confirm tileManager.js still does **not** import windowDrag.js

STOP. Do not start Phase 2 until approved.

================================================================
PHASE 2 — Notes close X + mobile CSS
Files (2): static/js/notes.js, static/style.css
================================================================

4) static/js/notes.js ~1210

After `#notes-fullscreen-toggle`, still inside `.notes-pane-header`, add:

```html
<button class="close-btn" id="notes-close" title="Close" aria-label="Close notes">✖</button>
```

In the template this is a JS template string. Use the same `\u2716` or `✖` Documents uses (`documentLibrary.js` ~1921 uses `\\u2716` in the template). Prefer `\u2716` inside the notes template string so encoding is unambiguous:

```javascript
<button class="close-btn" id="notes-close" title="Close" aria-label="Close notes">\u2716</button>
```

Wire next to the existing min/fs listeners (~1274–1285):

```js
  const closeBtn = document.getElementById('notes-close');
  if (closeBtn) closeBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    closePanel();
  });
```

Do **not** pass `'down'`. Do **not** change `#notes-minimize-btn` behavior.

5) static/style.css

`.modal-minimize-btn` already exists ~813. Add immediately after that rule (~831), not a new visual language:

```css
    .modal-fullscreen-btn { margin-right: 4px; }
    @media (max-width: 768px) {
      .modal-fullscreen-btn,
      [data-fullscreen-toggle] { display: none !important; }
    }
```

Notes already hides `#notes-fullscreen-toggle` at ~31260 and ~32155. Leave those rules. Do not hide `#notes-close` on mobile.

PHASE 2 VERIFY
- `node --check static/js/notes.js`
- Grep notes.js: `id="notes-close"` and `closePanel()` with no `'down'` in that listener
- Grep notes.js: `#notes-minimize-btn` listener still calls `closePanel('down')`
- Grep style.css: `.modal-fullscreen-btn`

STOP. Do not start Phase 3 until approved.

================================================================
PHASE 3 — pane-style close X (FormFlow, Story Canvas) + Documents skipSelector
Files (3): static/js/formflow.js, static/js/storyCanvas.js, static/js/documentLibrary.js
================================================================

6) static/js/formflow.js ~363–365

After `#ff-minimize-btn`, add:

```html
<button class="close-btn" id="ff-close" title="Close" aria-label="Close FormFlow">\u2716</button>
```

`#ff-exit-btn` stays. It is the in-form “leave this form?” control (`display:none` until a form is open). Do not reuse it as the window X.

Find the existing `#ff-minimize-btn` click listener (search `ff-minimize-btn`) and add beside it:

```js
  pane.querySelector('#ff-close')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    closePanel();
  });
```

Full close, no `'down'`.

7) static/js/storyCanvas.js ~109–111

After `#sc-minimize-btn`, add:

```html
<button class="close-btn" id="sc-close" title="Close" aria-label="Close Story Canvas">\u2716</button>
```

Wire beside the existing `#sc-minimize-btn` listener (~138–142):

```js
  _pane.querySelector('#sc-close')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    closeStoryCanvas();
  });
```

8) static/js/documentLibrary.js ~2139

`skipSelector: '.modal-close'` misses `#doclib-close.close-btn`, so dragging can start from the X. Change to:

```js
skipSelector: '.close-btn, .modal-close, .modal-minimize-btn, button, input, select',
```

Do **not** change `enableFullscreen: false`. Do **not** rewrite `enterFullscreen`. Phase 1 inject gives Documents the square; click uses `toggleMaximize` because `enableFullscreen` is false.

PHASE 3 VERIFY
- `node --check` on the three files
- Grep formflow: `id="ff-close"` and listener calls `closePanel()` with no `'down'`
- Grep storyCanvas: `id="sc-close"` and `closeStoryCanvas()` with no `'down'`
- Grep documentLibrary: `enableFullscreen: false` still present; skipSelector includes `.close-btn`

STOP.

================================================================
PHASE 4 — mechanical acceptance (no more code unless a check fails)
================================================================

Manual desktop checks (viewport > 768):

1. Notes: header ends `_` · square · `✖`. Square still toggles `notes-window-fullscreen` (existing Notes path; inject skipped because `#notes-fullscreen-toggle` exists). `✖` removes the pane (not a dock chip). `_` still minimizes to a chip.
2. Documents: header ends `_` · square · `✖`. Square maximize fills the area **beside** the icon rail, not over it. `✖` still closes. Top-edge windowDrag snap stays off; tileManager drag-to-top may still maximize — that is pre-existing, do not “fix”.
3. Calendar, Tasks, Gallery, Agent Bin, Cookbook, Settings, Memory, Theme, Email, Split-chat, Research: each header that goes through `makeWindowDraggable` shows the square between `_` and `✖` (or after `_` if that tool already had both). Clicking square maximizes to the rail-safe rect (except split-chat/email which keep custom FS callbacks).
4. FormFlow / Story Canvas: `_` · square · `✖`. `✖` full-closes. `_` still `closePanel('down')` / `closeStoryCanvas('down')`.
5. Mobile ≤768: square hidden; X still visible on Notes and Documents.
6. CMD Center: unchanged (no new X, no new square).

Grep guard — diff should ONLY touch:
- static/js/tileManager.js
- static/js/windowDrag.js
- static/js/modalManager.js
- static/js/notes.js
- static/style.css
- static/js/formflow.js
- static/js/storyCanvas.js
- static/js/documentLibrary.js

If you touched anything else, revert it.

ACCEPTANCE
- [ ] Chrome order `_` · square · X on Notes, Documents, and other makeWindowDraggable tool windows
- [ ] Notes X full-closes; Notes `_` still minimizes
- [ ] Documents square uses rail-safe maximize, not 100vw overlay
- [ ] Documents `enableFullscreen: false` unchanged
- [ ] FormFlow + Story Canvas gained X
- [ ] CMD / nested dialogs / document editor untouched
- [ ] Mobile hides maximize, keeps X
- [ ] `node --check` clean on every edited js file
- [ ] No new dependencies

END PROMPT
````

---

## Related agent sessions (last 48 hours)

Catalogued 2026-08-20 from Odysseus IDE transcripts (cutoff 2026-08-18 07:55). Resume in CLI: `agent --resume="<id>"`. This catalog chat omitted. Nested `subagents/` runs omitted.

Grouped by **what was edited or modified**, not by chat start time.

### Panel window chrome (this spec)

| When | What changed | Session | Resume |
|---|---|---|---|
| Aug 18 09:29 | Notes: add fullscreen square to the right of minimize (origin of this work) | [Notes fullscreen button](eb91e88e-1ee5-4123-9142-2f9bd5bf30a7) | `eb91e88e-1ee5-4123-9142-2f9bd5bf30a7` |
| Aug 20 07:47 | Spawn parallel implementers for `_` · square · X across panels | [Panel chrome parallel](af052624-3caf-4633-bc8c-9a551a814199) | `af052624-3caf-4633-bc8c-9a551a814199` |
| Aug 20 07:36 | Phase 2: Notes X + mobile hide FS (`notes.js`, `style.css`) | [Phase 2 notes CSS](fc64290d-660f-445c-98ab-64788e1b60de) | `fc64290d-660f-445c-98ab-64788e1b60de` |
| Aug 20 07:36 | Phase 3: FormFlow / Story Canvas X; Documents skipSelector (`formflow.js`, `storyCanvas.js`, `documentLibrary.js`) | [Phase 3 pane close](9975f111-aa4f-469a-896f-dc7e12e2ecc2) | `9975f111-aa4f-469a-896f-dc7e12e2ecc2` |

### Notes panel architecture

| When | What changed | Session | Resume |
|---|---|---|---|
| Aug 20 07:18 | Notes data dictionary / architecture map; reimagine the pane (`notes.js`, this handoff) | [Notes architecture map](ee0ee3bf-c8c0-4022-992e-4e607a823eb5) | `ee0ee3bf-c8c0-4022-992e-4e607a823eb5` |

### CMD Center / Vault

| When | What changed | Session | Resume |
|---|---|---|---|
| Aug 20 07:47 | Vault as Jarvis voice assistant → prosperity loop (`cmdCenter.js`) | [Vault Jarvis assistant](5411c0c9-4fde-45e5-8bf6-66c0e2e4e0a5) | `5411c0c9-4fde-45e5-8bf6-66c0e2e4e0a5` |
| Aug 20 06:30 | CMD hero + status-legend placement (`#cmd-hero`, `#cmd-scene-auto`) | [CMD hero legend](bc0c9990-6c9e-4e7d-982a-d6a11d66644e) | `bc0c9990-6c9e-4e7d-982a-d6a11d66644e` |
| Aug 19 15:32 | HQ AsyncAPI / left-rail phases (`cmdCenter.js`) | [HQ async API](6aa38dea-88f8-4ab0-be39-6ff043168a77) | `6aa38dea-88f8-4ab0-be39-6ff043168a77` |
| Aug 18 20:22 | CMD domain-tab audit; cleaner UI, less clutter (openspec-explore) | [CMD tab declutter](8d74daf4-4f9f-4c1c-8dd9-e3b964020419) | `8d74daf4-4f9f-4c1c-8dd9-e3b964020419` |
| Aug 18 14:43 | Audio brief / CMD Center play (Top 1 + Top 2) | [CMD audio brief](feee0f78-a879-4b39-9c99-514ef7e381fa) | `feee0f78-a879-4b39-9c99-514ef7e381fa` |

### Story Canvas

| When | What changed | Session | Resume |
|---|---|---|---|
| Aug 18 21:35 | Visual Story Canvas: paste image, quick text, research-in-pane; open-design + v0 prototype | [Story canvas visuals](dc078b53-5edc-423c-b4a8-d7c42f4057cf) | `dc078b53-5edc-423c-b4a8-d7c42f4057cf` |
| Aug 18 14:44 | Image annotator: white text notes beside image, arrows (`apps/story-canvas`) | [Canvas image annotator](71dcd60c-72bd-418e-9cba-efd13bc6066b) | `71dcd60c-72bd-418e-9cba-efd13bc6066b` |

### Chat session loading

| When | What changed | Session | Resume |
|---|---|---|---|
| Aug 18 14:37 | Always-load Odysseus chat sessions; diagnose slow load, then implement | [Always-load sessions](0129f65e-2912-44b0-a9f5-96981c9e3651) | `0129f65e-2912-44b0-a9f5-96981c9e3651` |

### Research reports / listen modal / skills

| When | What changed | Session | Resume |
|---|---|---|---|
| Aug 19 09:31 | Slash skill so outputs are dynamic HTML (Deep Research podcast-style) | [Dynamic HTML skill](ed7f53c2-4bb2-4e8b-9693-8b99f6892ce8) | `ed7f53c2-4bb2-4e8b-9693-8b99f6892ce8` |
| Aug 18 12:59 | Listen modal: Download button + playback speed | [Listen modal controls](c9f3769e-aa55-44c7-a473-a6ce9e7c4097) | `c9f3769e-aa55-44c7-a473-a6ce9e7c4097` |
| Aug 18 12:24 | Audit research report `rp-db8ce6a0bbcb` and pipelines (`research/panel.js`) | [Research pipeline audit](9fb62504-288e-4904-b080-85403f26ea21) | `9fb62504-288e-4904-b080-85403f26ea21` |

### Open Design / workspace surface

| When | What changed | Session | Resume |
|---|---|---|---|
| Aug 20 07:46 | Connect `open-design`; clean workspace surface for attention + action (`docs/agentic-life-os-build-spec.md`) | [Open-design workspace](b8b720f3-a1bf-42f8-85a5-7ddb673c9e8c) | `b8b720f3-a1bf-42f8-85a5-7ddb673c9e8c` |

### CEO brief / handoffs / stuck UI

| When | What changed | Session | Resume |
|---|---|---|---|
| Aug 20 07:19 | Restore CEO Brief to full-picture format | [CEO brief restore](4750f6e9-8d9c-4213-aa00-572cda5c8719) | `4750f6e9-8d9c-4213-aa00-572cda5c8719` |
| Aug 18 17:47 | Pick up handoff `ca5861b4`; archive related note/doc | [Handoff ca5861b4](82aec051-16af-46c8-820e-604b527e869f) | `82aec051-16af-46c8-820e-604b527e869f` |
| Aug 18 17:47 | Execute Odysseus handoff relay packet | [Handoff relay](ac65b3c2-faac-4f97-92d6-4154a4497a0f) | `ac65b3c2-faac-4f97-92d6-4154a4497a0f` |
| Aug 18 16:33 | Stuck overlay/screen; how to dismiss | [Stuck screen dismiss](78a6f454-c96b-472c-a404-56d1b79508eb) | `78a6f454-c96b-472c-a404-56d1b79508eb` |

For this chrome work, resume **Phase 2** / **Phase 3** first if verifying implementation; resume **Notes fullscreen button** if you need the original request.

---

## Prompt-craft notes

Shaped this way because a weaker builder will otherwise (a) flip Documents `enableFullscreen: true` and cover the sidebar, (b) copy-paste Notes’ `_enterNotesFullscreen` into 12 files, (c) wire Notes X to `closePanel('down')` and make two minimize buttons, (d) inject a second `_` into Notes because the fullscreen control already uses `.modal-minimize-btn`.

Validation tools: Read/Grep on `notes.js`, `documentLibrary.js`, `windowDrag.js`, `modalManager.js`, `tileManager.js`, `calendar.js`, `tasks.js`, `gallery.js`, `formflow.js`, `storyCanvas.js`, `splitChat.js`, `research/panel.js`, `cmdCenter.js`, `style.css` (~813, ~31260, ~32155), `package.json` (no tsc/eslint).

Do not implement in this chat unless asked — this file is the deliverable.
