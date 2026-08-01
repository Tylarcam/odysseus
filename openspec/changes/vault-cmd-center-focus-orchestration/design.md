## Context

V.A.U.L.T. (`services/home/cmd_center.py` + `static/js/cmdCenter.js` and friends) shipped in phases (P2–P5, see `.tmp/hq-phases/`). Each phase added a new place to show "what needs attention" — priority queue (P1/P2), hero + stage cards (P2/P3), pill badges + AI Wire (P4), directive triage swipe stack (separate change), live polling (P5) — without a pass that asked "does this item still need its *own* slot once the other five panels already show it." The payload today (`build_cmd_center` in [cmd_center.py](../../../services/home/cmd_center.py)) already contains two hand-patched dedup rules (Vault Sync skipped from `suggested_commands` because the header clock covers it; Plan Today skipped from `suggested_commands` because the stage card covers it) — proof the team already knows duplication is a problem, just without a general mechanism.

Separately, desktop's 7 `TAB_LAYOUT` domain tabs and mobile's 4-tab bar (`HUD`/`Queue`/`Commands`/`Wire`) evolved independently and were never reconciled — `CORE` alone already renders most of what the other 6 tabs show filtered subsets of.

This design covers four independent-but-related fixes, all in service of one goal: an operator glances at the vault, finds the one thing to do, does it, and leaves — without cross-checking five panels or hitting dead affordances.

## Goals / Non-Goals

**Goals:**
- One directive/signal → exactly one actionable ("do this now") slot, everywhere else is passive/status-only.
- One navigation mental model that works the same way (bigger/smaller, not different) on desktop and mobile.
- Space-hold and Esc do what the UI already claims they do.
- Idle vault (nothing changed since last poll) does not pay full DB + IMAP + MemPalace rebuild cost every 30s.

**Non-Goals:**
- Not redesigning the visual language (CRT/terminal aesthetic, colors, chip styles) — this is information architecture and interaction wiring, not a reskin.
- Not touching the Directive Triage swipe modal's own logic (`cmdCenterDirective.js`) beyond registering it as a focus-owning surface for the new global keyboard handlers.
- Not building a generic pub/sub or state-management framework — the registry is a plain data structure computed once per payload build, not a new runtime system.
- Not changing which underlying data sources feed the vault (notes, handoffs, jobs, etc.) — only where/how many times their derived signals are rendered.

## Decisions

### 1. Signal registry lives server-side, in `build_cmd_center`

**Decision**: Add a single pass at the end of `build_cmd_center` that assigns each directive-worthy item (from `priority_queue`) a `primary_slot` (`"hero"` | `"stage_card:<id>"` | `"deck:<cmd_id>"` | `None`) and tags every rendering of that same item elsewhere with `dedup_key` = the item's stable id. `commands`, `suggested_commands`, and `stage_cards` entries carry `dedup_key` when they represent a specific item (not a generic static action like "Notes" or "Calendar").

**Why server-side, not client-side**: the ranking logic (`_build_priority_queue`, `_build_hero`) already lives in Python and already knows urgency order. Duplicating that ranking in JS to decide "is this the primary slot" would create a second source of truth that can drift from the hero/queue the server already computed. The frontend's job becomes purely mechanical: if an entry has `dedup_key` X and X's `primary_slot` isn't this panel, render it passively (no button, or omit it) instead of as a CTA.

**Alternatives considered**:
- *Client-side dedup by scanning rendered DOM ids*: rejected — fragile, order-dependent, and duplicates ranking logic the backend already owns.
- *Just delete panels*: rejected — the panels serve different purposes (glanceable status vs. actionable). The fix is making the *non-primary* renderings explicitly non-actionable, not removing them.

**Mechanism**: passive echoes (pill dot, branch_health row, wire ticker line) already render without a distinct CTA button in most cases today — they're click-to-navigate, not "resolve this" actions. The registry only needs to strip actionability from `commands`/`suggested_commands`/`stage_cards` entries that duplicate the current hero item, since those three are the ones generating competing CTAs. Concretely: `suggested_commands` never includes a `dedup_key` that matches `hero.dedup_key`; `stage_cards` other than the one matching `hero.dedup_key` render as informational (still clickable — it's still useful navigation — but no longer described as "the next action").

### 2. Mobile's 4-tab grouping becomes canonical; desktop domain tabs become a filter within `HUD`

**Decision**: Keep `HUD`, `Queue`, `Commands`, `Wire` as the top-level concept on both breakpoints. On desktop, `HUD` gains a secondary filter strip (the existing 7 domain-tab labels: CORE/MEM/PROD/COMMS/AGENCY/RELAY/MYCELIA) that filters *within* the HUD view rather than swapping to an entirely different left/right panel composition. `Queue` = today's priority_queue/directive rail (filterable by the same domain labels). `Commands` = today's command deck. `Wire` = today's AI Wire, full-width.

**Why this direction and not the reverse (desktop's 7 tabs become canonical, mobile grows to match)**: mobile's constraint (screen space) already forced the simpler, more honest grouping — "what's happening" / "what needs me" / "what can I do" / "what just happened" is a smaller, more memorable model than 7 domain names, and it matches how the operator actually decides what to look at (by *kind of question*, not by *which internal branch owns the data*). Desktop has room to *additionally* filter by domain, so domain becomes a lens on top of the 4-question model rather than a competing nav axis.

**Alternatives considered**:
- *Keep both, unreconciled*: rejected — this is finding #2 from the review; the point is to stop it.
- *Collapse to domain tabs everywhere, mobile scrolls*: rejected — 7 tabs on a narrow viewport is worse information density than today's 4, moving backward on mobile to fix desktop.

**Persistence**: one `localStorage` key (`odysseus-cmd-view`) replaces the current pair (`odysseus-cmd-domain-tab` used only on desktop, implicit tab state on mobile), storing `{ view: 'hud'|'queue'|'commands'|'wire', domainFilter: 'CORE'|... }`. Desktop reads both fields; mobile reads only `view` (domain filter defaults to `CORE`/all when not shown).

### 3. Global keyboard handlers are focus-scoped, not window-global

**Decision**: Bind `keydown` on `document` for `Escape` and `Space`, but gate both behind a shared "does anything else own input right now" check: skip when `document.activeElement` is a text input/textarea/contenteditable, when `isDirectiveTriageOpen()` is true (its own Esc handler already owns that context), or when any other modal sets a `data-cmd-modal-open` marker on `<body>`. Space-hold uses `keydown`→start timer, `keyup`/`blur`→cancel, firing `_activateVoiceDelegate()` only past a 3000ms threshold (matching the copy). Esc calls the existing minimize path used by `#cmd-center-minimize`'s click handler.

**Why gate on a marker attribute instead of importing each modal module**: `cmdCenter.js` already has import-order and circular-dependency sensitivity (see the P5 assembly note about not importing `cmdCenterLive.js` prematurely). A `data-cmd-modal-open` attribute any modal can set/clear on open/close is a zero-import way for `cmdCenterDirective.js` (and any future modal) to claim focus without `cmdCenter.js` needing to know about every modal module's API.

**Alternatives considered**:
- *Only bind when vault root has focus*: rejected — operators expect Space-hold-to-talk to work whether or not they last clicked inside the vault, matching a walkie-talkie mental model, and the vault is a fixed-position overlay when open.
- *Use `keypress`*: rejected — deprecated, inconsistent modifier-key behavior.

### 4. Poll short-circuit via content hash, not HTTP caching headers

**Decision**: `build_cmd_center` computes a stable hash (e.g. `hashlib.sha1` over a canonical JSON of everything except `synced_at`/`globe_graph`) and includes it as `payload_hash`. The route accepts an optional `?since_hash=<value>` query param; if the freshly computed hash matches, it returns a minimal `{"unchanged": true, "synced_at": ...}` instead of the full payload. `cmdCenterLive.js`'s `fetchData` passes the last-seen hash and its `applyUpdate` becomes a no-op (just bumps the sync label) when `unchanged` is true. This still requires running the DB queries to compute the hash — the win is skipping `build_globe_graph()` (the most expensive step) and skipping full JSON re-serialization/re-render on the client, not skipping the DB round-trip itself.

**Why not real HTTP `ETag`/`304`**: the DB queries still have to run to know if anything changed (there's no cheap "last modified" watermark spanning notes/docs/tasks/handoffs/jobs today), so a true `304` saves the same amount of backend work as a 200-with-hash-match — but standard `ETag`/`If-None-Match` semantics fight with `fetch`'s default caching behavior and add a second code path (browser cache vs. app-level state) to reason about. A plain JSON field keeps the contract explicit and testable.

**Why `globe_graph` moves off the hot path regardless of hash match**: it's the single most expensive step (`fetch_mempalace_globe_graph()` is a network call to MemPalace) and it changes far less often than notes/tasks. It's refetched only when: (a) the payload hash actually changed AND the globe/CORE view is the active view, or (b) on an explicit user action (opening the vault, switching to a view that shows the globe, manual Vault Sync). `cmdCenterLive.js` passes a `include_globe` flag reflecting current view.

**Alternatives considered**:
- *Client-side debounce/backoff only (already exists via `cmdCenterLive.js` failure backoff)*: doesn't address the idle-but-online case, which is the common case (vault open, operator reading, nothing changed).
- *WebSocket/SSE push instead of polling*: bigger architectural change, out of scope for this pass; polling with a cheap short-circuit gets most of the win without a new transport.

## Risks / Trade-offs

- **[Risk] Registry under-suppresses and an item still shows in 2+ CTA slots** → Mitigation: `tests/test_home_dashboard.py` asserts, for each `priority_queue` item, `dedup_key` appears as an actionable entry in at most one of `hero`/`stage_cards`/`suggested_commands`.
- **[Risk] Registry over-suppresses and an item disappears from all CTA slots (operator can't find it)** → Mitigation: every item stays visible somewhere passively (priority_queue rail itself is never filtered by the registry — it's the ground truth list); the registry only trims *duplicate CTAs*, never the queue.
- **[Risk] Reconciled nav model changes muscle memory for the existing user** → Mitigation: `odysseus-cmd-domain-tab` (old key) is read once as a migration fallback into the new `odysseus-cmd-view` key, so an existing preference (e.g. "I always land on RELAY") carries forward as the new domain filter default instead of resetting to CORE.
- **[Risk] Space-hold conflicts with browser/OS behavior (scroll-on-space, other page shortcuts)** → Mitigation: `preventDefault()` only fires once the hold exceeds ~150ms and the vault is open, so a quick incidental Space (e.g. focus was on a checkbox) doesn't get hijacked or block normal page scroll when the vault isn't open.
- **[Risk] Hash short-circuit hides a real backend error as "unchanged"** → Mitigation: hash is computed from freshly-fetched data on every request (never cached across requests), so a query failure still raises/propagates through the existing error path before hash computation — `unchanged: true` only ever means "computed successfully and it matches," never "skipped computing."
- **[Trade-off] Hash short-circuit doesn't reduce DB load, only globe-graph + JSON-payload + client-render cost** → Accepted: still the single biggest, cheapest win (globe_graph is the most expensive step and the JSON payload is the largest), and a full "don't touch the DB at all" cache would need a change-tracking mechanism spanning 6+ tables that's disproportionate to this change's scope.

## Migration Plan

1. Land the signal registry + `dedup_key` field changes in `cmd_center.py` behind existing tests passing (additive field, no payload shape removal) — deployable independently.
2. Land frontend registry-aware rendering in `cmdCenter.js` reading `dedup_key`/`primary_slot` (falls back to today's "always render" behavior if fields are absent, so frontend/backend can deploy slightly out of order).
3. Land the nav-model reconciliation (new `odysseus-cmd-view` key with fallback read of the old key) — purely client-side, no backend dependency.
4. Land keyboard handlers — purely additive, client-side only.
5. Land the poll short-circuit — backend accepts `since_hash`/`include_globe` as optional params (defaults preserve today's full-payload behavior), then wire `cmdCenterLive.js` to send them.
6. Delete dead code (`_startSoftRefresh` family) and fix the stale comment, once step 3–5 land and there's no risk of needing the old poll path as a fallback.
7. Update `docs/vault-cmd-center-component-atlas.md` last, once behavior is final, since it's documentation of the shipped state.

Rollback: every step above is additive or purely client-side except the dead-code deletion (step 6), which is trivially revertible via git and has no runtime dependents by construction.

## Open Questions

- Should the domain-filter strip on desktop `HUD` be visible on mobile `HUD` too (as a secondary row) once there's enough vertical space (tablet breakpoint), or stay desktop-only? Deferred to implementation — start desktop-only, revisit if tablet width usage data suggests otherwise.
- Should `Space`-hold have a visible countdown/progress affordance (e.g. a ring around the audio icon) so the 3s threshold is discoverable without reading the hint text? Recommended yes, but treated as a nice-to-have polish task, not blocking for this change.
