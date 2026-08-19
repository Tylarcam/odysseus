## 1. Backend attention stack

- [x] 1.1 Add `_build_attention_stack` in `services/home/cmd_center.py` (handoffs → jobs review/ready → overdue notes)
- [x] 1.2 Include `attention_stack` on `build_cmd_center` return payload
- [x] 1.3 Extend `tests/test_home_dashboard.py` for stack presence, ordering, overdue fields

## 2. Triage modal module

- [x] 2.1 Create `static/js/cmdCenterDirective.js` with open/close, card render, desktop Delegate/Done/Open
- [x] 2.2 Implement mobile horizontal swipe (left=delegate, right=done) with axis cancel + in-flight lock
- [x] 2.2b Implement mobile double-tap to peek/cycle the stack without delegate or done (wraps; swipe still wins)
- [x] 2.3 Persist last handoff target in localStorage; show target chips on card

## 3. Actions

- [x] 3.1 Wire Delegate → `createHandoffDocument` (non-handoff kinds); handoff kind → Agent Bin
- [x] 3.2 Wire Done → note archive/clear due, job mark-applied, handoff resolve
- [x] 3.3 On success: advance stack + callback parent refresh; on empty stack close modal

## 4. CMD Center entry

- [x] 4.1 Intercept hero/CTA clicks in `cmdCenter.js` to open triage when `attention_stack` non-empty
- [x] 4.2 Pass refresh callback that refetches cmd-center and updates hero/panels in place when possible

## 5. Verify

- [x] 5.1 Run `pytest tests/test_home_dashboard.py` and fix failures
- [x] 5.2 Restart Odysseus container so Python payload is live; smoke-open vault triage once
