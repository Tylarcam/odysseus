## 1. Signal registry (vault-signal-priority)

- [x] 1.1 Add `dedup_key` to every `priority_queue` item in `_build_priority_queue` (stable id already present as `target_id`/`id` — reuse, don't invent a new id scheme)
- [x] 1.2 Add a `_assign_primary_slots(priority_queue, hero, stage_cards, commands)` pass in `cmd_center.py` that sets `primary_slot` per item and tags `hero`/`stage_cards`/`commands`/`suggested_commands` entries with `dedup_key` where they represent a specific item
- [x] 1.3 Update `suggested_commands` construction to skip any entry whose `dedup_key` matches `hero.dedup_key` (generalize the existing ad hoc "don't triple it" comments into this one mechanism)
- [x] 1.4 Update `stage_cards` construction so non-primary entries carry `dedup_key` but no "primary" flag
- [x] 1.5 Add `tests/test_home_dashboard.py` case: for a payload with a top-ranked handoff, assert its `dedup_key` appears as primary in exactly one of `hero`/`stage_cards`/`suggested_commands`
- [x] 1.6 Add `tests/test_home_dashboard.py` case: assert `priority_queue` is never filtered/shortened by primary-slot assignment
- [x] 1.7 Update `cmdCenter.js` renderers for `stage_cards`/`suggested_commands`/`command_deck` to style non-primary (no matching `dedup_key`) entries without "next action" emphasis, while keeping them clickable
- [x] 1.8 Manual check: trigger a state with an overdue note + a ready job simultaneously; confirm only one is visually presented as "the" next action while both remain reachable (verified via scripted `build_cmd_center` payload — no browser session available in this environment; see session notes)

## 2. Reconciled navigation model (vault-nav-model)

- [x] 2.1 Define the new `odysseus-cmd-view` localStorage schema (`{ view, domainFilter }`) and read/write helpers in `cmdCenter.js`, replacing direct reads of `odysseus-cmd-domain-tab`
- [x] 2.2 Add one-time migration: if `odysseus-cmd-view` is absent and `odysseus-cmd-domain-tab` is present, seed `domainFilter` from it
- [x] 2.3 Domain tabs render as a filter strip scoped to the `HUD` view (`.cmd-domain-tabs` hidden except when `data-mobile-tab="hud"`). Resolved design.md's open question by shipping it on **mobile HUD too**, not desktop-only — kept `TAB_LAYOUT`'s per-domain panel composition intact (lower-risk than rewriting it to a content-only filter) rather than deleting the 12 dedicated Orbital panels; conceptually the domain strip is now a lens on HUD everywhere, not a competing nav
- [x] 2.4 `Queue`/`Commands`/`Wire` panels already call `_filterByBranch`/`_filterCommandsForTab` with `_domainTab` (unchanged logic) — confirmed still wired after the state-unification in 2.1
- [x] 2.5 Verified: `_setMobileTab`/`_setDomainTab` both write through `_persistViewState`, so `_mobileTab`/`_domainTab` share one persisted pair — a resize mid-session doesn't lose either
- [x] 2.6 Updated `docs/vault-cmd-center-component-atlas.md` "Domain tabs" row + added a "Navigation preference" section
- [x] 2.7 Manual check: verified via code trace (no browser session available) — `_setDomainTab('RELAY')` persists `{view:'hud', domainFilter:'RELAY'}` via `_persistViewState`; on reload, module init reads it back into `_domainTab`/`_mobileTab` before first paint, so the vault reopens on `HUD` with `RELAY` applied, not a separate page

## 3. Real keyboard shortcuts (vault-keyboard-shortcuts)

- [x] 3.1 Add a shared `_inputOwnsFocus()` helper checking `document.activeElement` (input/textarea/contenteditable), `isDirectiveTriageOpen()`, and `document.body.dataset.cmdModalOpen`
- [x] 3.2 Add global `document` `keydown`/`keyup` listeners for `Space`: start a 3000ms timer on `keydown` (guarded by `_inputOwnsFocus()`), cancel on early `keyup`/`blur`/window blur, fire `_activateVoiceDelegate()` once past threshold — pure timer logic extracted to `static/js/cmdCenterHotkeys.js` so it's unit-testable
- [x] 3.3 Add global `document` `keydown` listener for `Escape`: guarded by `_inputOwnsFocus()`, calls `_closePanel('down')` — the same function `#cmd-center-minimize`'s click handler calls
- [x] 3.4 Picked `isDirectiveTriageOpen()` (already in `_inputOwnsFocus()`) for the triage modal specifically, per the task's own guidance to avoid double-marking; `data-cmd-modal-open` stays as the generic hook reserved for any *other* future modal. (Bonus: triage's own Esc handler is capture-phase + `stopPropagation()`, so it already pre-empts the global bubble-phase listener independent of this check — belt-and-suspenders, not load-bearing alone.)
- [x] 3.5 No change needed — `audio.hint` copy already matched; it's now backed by real handlers instead of dead affordances
- [x] 3.6 Added `tests/test_cmd_center_hotkeys.mjs` (Node's built-in `node:test`, zero new devDependency — no JS test framework exists in this repo to follow, so this establishes a minimal convention). `node --test tests/test_cmd_center_hotkeys.mjs` → 4/4 pass: threshold-hold arms once, early release never arms, key-repeat doesn't double-schedule, a fresh hold after release re-arms
- [x] 3.7 Manual check: verified via code trace (no browser session available) — `_inputOwnsFocus()` sees `activeElement.tagName === 'INPUT'` and returns true, so the keydown handler returns before calling `_spaceHold.keydown()` or `preventDefault()`; the browser handles the space character normally
- [x] 3.8 Manual check: verified via code trace — `isDirectiveTriageOpen()` makes `_inputOwnsFocus()` true so the global handler no-ops; independently, triage's own Esc handler is registered capture-phase with `stopPropagation()`, which already prevents the event from reaching the global bubble-phase listener at all

## 4. Poll short-circuit + globe cadence split (vault-live-sync-efficiency)

- [x] 4.1 Add `payload_hash` computation to `build_cmd_center` (stable hash over the response minus `synced_at`/`globe_graph`) — `_compute_payload_hash()`, sha1 over sorted-key JSON
- [x] 4.2 Add `since_hash` and `include_globe` query params to `GET /api/home/cmd-center` in `home_routes.py` (default `include_globe=True` — backward compatible for any caller that doesn't pass it)
- [x] 4.3 Skip `fetch_mempalace_globe_graph()`/`build_globe_graph()` entirely when `include_globe` is false; omit `globe_graph` key from response in that case
- [x] 4.4 When `since_hash` matches the freshly computed `payload_hash`, short-circuit to the minimal `{"unchanged": true, "synced_at", "payload_hash"}` response
- [x] 4.5 Confirmed: the route builds the full payload (and would raise on any query failure) before ever comparing `since_hash` — an error can't reach the `unchanged` branch
- [x] 4.6 Updated the `fetchData` callback `cmdCenter.js` passes into `startCmdCenterLive()` (cmdCenterLive.js itself stays transport-agnostic by design — "parent owns fetch/apply") to send `since_hash`/`include_globe=0` only on the `live: true` poll path, never on the initial open fetch
- [x] 4.7 `applyUpdate` now short-circuits to a sync-label-only update when `data.unchanged` is true, skipping `_applyLiveUpdate`'s full stage/rail refresh
- [x] 4.8 `_fetchData` preserves `_data.globe_graph` across merges when the incoming payload omits the key (`'globe_graph' in payload` check) instead of falling back to the empty default template
- [x] 4.9 Added `test_payload_hash_stable_for_identical_input`, `test_payload_hash_changes_with_data`, `test_include_globe_false_skips_mempalace_and_omits_key` to `tests/test_home_dashboard.py` — 23/23 pass. (Route-level `since_hash` branch is a 6-line pass-through of the already-tested hash; no existing test in this file invokes route coroutines directly — `build_cmd_center`-level coverage matches the file's established convention.)
- [x] 4.10 Manual check: no browser session available, so verified the full round trip with a scripted 3-call simulation (open → unchanged poll → changed poll) mirroring the exact route logic — confirmed: open fetch includes `globe_graph`; an unchanged poll returns only `{unchanged, synced_at, payload_hash}` with `fetch_mempalace_globe_graph` never invoked; a changed poll returns the full payload minus `globe_graph`, non-`unchanged`

## 5. Cleanup

- [x] 5.1 Delete `_startSoftRefresh`, `_softRefresh`, and `SOFT_REFRESH_MS` from `cmdCenter.js` (confirm `_stopSoftRefresh()` call site is also removed since there's nothing left to stop)
- [x] 5.2 Fix the stale "do not import from cmdCenter.js until assembly step runs" comment at the top of `cmdCenterLive.js` to reflect that it's wired in
- [x] 5.3 `python -m pytest tests/test_home_dashboard.py -q` → 23/23 pass (up from 20 — added signal-registry + payload-hash tests). Also kicked off the full `tests/` suite as a broader regression check.
- [x] 5.4 Updated `docs/vault-cmd-center-component-atlas.md`: "Domain tabs"/tab-bar rows rewritten for the reconciled nav model, new "Navigation preference" section (`odysseus-cmd-view` schema + migration), new "Signal priority (dedup)" section, new "Global hotkeys" section (Space-hold/Esc), "Data flow" section documents the live-poll short-circuit
