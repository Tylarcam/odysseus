## Why

V.A.U.L.T. was built by layering phases (P2–P5) on top of each other, and each phase added its own way to surface "what needs you next" — the result is a dashboard where a single handoff or job can compete for attention in up to 8 places at once (pill, branch row, priority queue, hero, stage card, command deck, suggested commands, wire ticker), desktop and mobile teach the operator two unrelated navigation models, and the UI promises keyboard shortcuts (Space-hold, Esc) that don't exist. None of this is a functional bug — the vault works — but it actively works against the thing it's for: letting the operator see the one next action, act on it, and get back to work with minimal reconciliation and re-orientation cost. This change makes "one signal, one next-action slot" and "one navigation model" load-bearing rules instead of ad hoc per-panel decisions, and closes the two credibility gaps (fake shortcuts, wasteful poll cost) that erode trust in the surface while we're in the code.

## What Changes

- Introduce a server-owned **signal registry**: every directive-worthy item (handoff, job, overdue/pinned note, active task) is assigned exactly one "primary" surface (hero when it's the top-ranked item, else its stage-card/deck slot) plus passive-only status indicators elsewhere (pill dot, branch row, wire ticker) that carry no independent CTA. `commands`/`suggested_commands`/`stage_cards` stop each independently deciding whether to show an item — they ask the registry.
- Reconcile desktop (7 domain tabs) and mobile (4-tab bar) into one explicit model: mobile's 4 tabs become the canonical top-level grouping (`HUD`, `Queue`, `Commands`, `Wire`), and desktop's 7 domain tabs are re-framed as an optional drill-down *within* `HUD` rather than a parallel top nav — CORE becomes the default landing view on both, and MEM/PROD/COMMS/AGENCY/RELAY/MYCELIA become named filters of the same view, not distinct destinations with their own re-derived layouts.
- Implement the two advertised keyboard shortcuts for real: global `Space`-hold (≥3s, ignoring text-input focus) arms voice delegate; global `Esc` (when no modal owns focus) minimizes/dismisses the vault. Both dispatch through the existing action pipeline (`_activateVoiceDelegate`, minimize) so there's one code path for mouse and keyboard.
- Add a poll short-circuit to `GET /api/home/cmd-center`: compute a content hash of the cheap-to-derive payload and return `304`/`{unchanged: true}` when nothing changed since the client's last synced hash, so the default 30s `cmdCenterLive.js` cadence stops paying full DB+IMAP+MemPalace cost when the vault is idle. Split `globe_graph` out of the hot poll path into a slower-cadence fetch (or on-demand when the globe tab is actually visible).
- **BREAKING (internal only)**: `commands`, `suggested_commands`, and `stage_cards` payload shape gains a `dedup_key` field so the frontend can enforce single-slot rendering; frontend code that assumed all three arrays render independently must switch to registry-filtered rendering.
- Delete dead code (`_startSoftRefresh`/`_softRefresh`/`SOFT_REFRESH_MS`) and fix the stale "do not import" comment in `cmdCenterLive.js` as part of the same pass, since both were found during this review and touch the same files.

## Capabilities

### New Capabilities

- `vault-signal-priority`: the single-source-of-truth rule for where a given directive/signal is allowed to render — one primary actionable slot, N passive/status-only echoes, computed server-side and enforced client-side.
- `vault-nav-model`: the reconciled desktop/mobile navigation model — mobile's 4-tab grouping as canonical, desktop domain tabs as a drill-down filter within `HUD`, with a single persisted "current view" concept shared across breakpoints.
- `vault-keyboard-shortcuts`: real global handlers for Space-hold-to-arm-voice and Esc-to-dismiss, scoped so they don't fire while the user is typing or a modal (e.g. directive triage) owns focus.
- `vault-live-sync-efficiency`: the poll short-circuit (content-hash based `unchanged` response) and the split cadence for `globe_graph`, so idle vaults stop paying full-rebuild cost every 30s.

### Modified Capabilities

- (none — no existing `openspec/specs/` entries cover V.A.U.L.T. today; the prior `vault-directive-triage` work landed as its own capability and is unaffected except that its modal must be recognized as focus-owning by `vault-keyboard-shortcuts`)

## Impact

- `services/home/cmd_center.py` — signal registry / dedup logic feeding `commands`, `suggested_commands`, `stage_cards`; content-hash computation for the poll short-circuit.
- `routes/home_routes.py` — `GET /api/home/cmd-center` gains `If-None-Match`/hash-based short-circuit handling; globe graph moved to its own cadence or query param.
- `static/js/cmdCenter.js` — registry-aware rendering (drop duplicate CTA rendering), unified nav-model wiring (domain tabs become a `HUD` sub-view, not a parallel top nav), global keydown handlers for Space/Esc, deletion of `_startSoftRefresh`/`_softRefresh`/`SOFT_REFRESH_MS`.
- `static/js/cmdCenterLive.js` — stale top-of-file comment fix; optional hash param passthrough for the short-circuit.
- `static/js/cmdCenterDirective.js`, `cmdCenterAudio.js` — register as focus-owning surfaces so global Esc/Space don't fire underneath an open modal or during active voice capture.
- `docs/vault-cmd-center-component-atlas.md` — update to describe the registry rule and the reconciled nav model (this doc is the mirror of `CMD_COMPONENT_ATLAS` and will otherwise go stale immediately).
- Tests: `tests/test_home_dashboard.py` (registry dedup, hash short-circuit) + frontend smoke checks for the new keyboard handlers.
