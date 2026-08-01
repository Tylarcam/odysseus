## Why

The V.A.U.L.T. hero CTA (“OPEN DIRECTIVE”) jumps straight into Notes/Jobs and skips triage. On mobile especially, the operator needs a fast stack of needs-attention items with one-gesture delegate vs done — without hunting through rails.

## What Changes

- Hero / primary-directive open path opens a **Directive Triage** modal instead of jumping to the first surface.
- Modal presents a **swipeable stack** of all needs-attention / overdue items (Tinder-style, one card at a time).
- **Swipe left (or Delegate):** create an Agent Bin / Relay handoff via existing `createHandoffDocument`.
- **Swipe right (or Done):** mark the item finished via kind-specific APIs (note archive/clear due, job mark-applied, handoff resolve).
- Desktop gets explicit Delegate / Done / Open buttons; mobile gets horizontal swipe with edge hints.
- CMD Center payload gains an `attention_stack` list so ranking stays server-owned.

## Capabilities

### New Capabilities

- `vault-directive-triage`: Directive triage modal — stack source, open entry points, swipe/button actions (delegate handoff vs mark finished), and post-action refresh of hero/count.

### Modified Capabilities

- (none — no existing main-spec coverage for vault directive open behavior)

## Impact

- `services/home/cmd_center.py` — build `attention_stack`
- `static/js/cmdCenterDirective.js` — new modal + swipe
- `static/js/cmdCenter.js` — intercept hero/CTA; open modal
- `static/js/handoff.js` — reuse `createHandoffDocument`
- Notes / jobs / agent-bin APIs for finish paths
- Tests: `tests/test_home_dashboard.py` (+ light JS/string checks as needed)
