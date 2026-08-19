## 1. Step 0 — dead code removal (separate commit, no behavior change)

Per the workspace Step 0 rule: `cmdCenter.js` is 4300 LOC and `cmd_center.py` is 1875 LOC. Clean before
restructuring, and commit the cleanup on its own.

- [ ] 1.1 Inventory unused exports, unused imports, dead props, and debug logs in `static/js/cmdCenter.js`; remove them
- [ ] 1.2 Inventory and remove dead code in `services/home/cmd_center.py`
- [ ] 1.3 Remove dead code in `static/js/cmdCenterAudio.js` and `static/js/cmdCenterScene.js`
- [ ] 1.4 Run `python -m pytest tests/test_home_dashboard.py` and confirm no behavior change
- [ ] 1.5 Commit the cleanup alone, before any task group 2 work begins

## 2. Server rationalization (additive, backward-compatible)

Delivers `vault-attention-rationalization`. Nothing renders differently yet — the payload gains fields.

- [ ] 2.1 Define the three salience tier identifiers and the tier-assignment function in `services/home/cmd_center.py`
- [ ] 2.2 Emit `consequence`, `response_time`, and `operator_action` for `priority_queue` items
- [ ] 2.3 Emit the same three fields for handoff, job, note, and task items wherever they enter the attention layer
- [ ] 2.4 Implement the rationalization gate: items missing any of the three fields get no `salience_tier` and are marked as detail
- [ ] 2.5 Implement the top-tier cap (max 3 concurrent) and the ~80/15/5 distribution target
- [ ] 2.6 Reclassify `_build_relay_stats` (`cmd_center.py:689`) output — keep all nine values, tier only those with an operator action
- [ ] 2.7 Add `attention_count` and override/dismiss rate recording for instrumentation
- [ ] 2.8 Extend `tests/test_home_dashboard.py`: rationalization fields present, gate rejects incomplete items, tier cap enforced, distribution targeted, relay stats demoted but retained, `priority_queue` still unfiltered

## 3. Registry extension and de-duplication

Delivers the `vault-signal-priority` delta. Depends on group 2 for tier data.

- [ ] 3.1 Extend `dedup_key` / `primary_slot` assignment to cover rail panel content, not only `commands` / `suggested_commands` / `stage_cards`
- [ ] 3.2 Add per-surface salience budgets and the collapse-to-count behavior for passive surfaces
- [ ] 3.3 Enforce "one fact at full emphasis per view" for the attention count across hero, glance chips, priority queue header, and CEO quick-read
- [ ] 3.4 De-duplicate Documents (CORE left rail vs MEM right rail, `TAB_LAYOUT` 129 vs 134)
- [ ] 3.5 De-duplicate AI Wire across CORE / MEM / PROD / COMMS to one presentation per view
- [ ] 3.6 De-duplicate agent activity across CORE swarm activity, AGENCY board, and MYCELIA activity
- [ ] 3.7 De-duplicate MYCELIA graph stats across `_renderMyceliaActivity` and `_renderMyceliaStats`
- [ ] 3.8 Verify collapsed items remain retrievable client-side without a new server request
- [ ] 3.9 Add tests for registry extension, collapse behavior, and each de-duplication above

## 4. Client tier-filtered rendering (behind a preference flag)

Gate the new surface behind the existing `odysseus-cmd-center-visibility` mechanism so the old surface
stays one toggle away for direct comparison.

- [ ] 4.1 Add a preference flag that switches between legacy and tier-filtered rendering
- [ ] 4.2 Implement tier-filtered rail rendering in `_renderPanelById`
- [ ] 4.3 Implement the fire rail (`Now` / `Next` / `Blocked`, max 3 items, each passing the rationalization test)
- [ ] 4.4 Implement the detail level so demoted values are reachable within two disclosure steps
- [ ] 4.5 Audit disclosure depth across the surface and remove any third nested level
- [ ] 4.6 Confirm the legacy surface still renders correctly with the flag off
- [ ] 4.7 Frontend smoke check: tier filtering, fire rail cap, two-level disclosure

## 5. Focus protocol

Delivers `vault-focus-protocol`. The core of the change and the first non-trivial revert, so it lands
after groups 2–4 are stable.

- [ ] 5.1 Define the focus object (`focused_entity`, `focused_edge`, `focus_source`, `focus_confidence`, `focus_timestamp`) as single-instance client state
- [ ] 5.2 Set focus on sphere node click with `focus_source` of `click`
- [ ] 5.3 Set focus from agent speech with `focus_source` of `agent`
- [ ] 5.4 Implement operator-precedence: operator focus set within a turn is not overwritten by agent focus
- [ ] 5.5 Re-point `_mapBriefHighlight` (`cmdCenter.js:2944`) to read from the focus object instead of brief-playback scope
- [ ] 5.6 Re-point `_speakNodeSummary` (`cmdCenter.js:3452`) to write to the focus object
- [ ] 5.7 Verify BRIEF ME still works end to end as one consumer of the protocol rather than its owner
- [ ] 5.8 Include the focus object in `GET /api/voice/vault-brief` context so Jarvis shares the referent
- [ ] 5.9 Resolve deictic references ("this one", "that") against the focused entity
- [ ] 5.10 Frontend smoke check: click-away-mid-utterance, deictic resolution, focus singleton

## 6. Sphere as degree-of-interest view

Delivers the remaining `vault-focus-protocol` requirements in `static/js/cmdCenterScene.js`.

- [ ] 6.1 Implement DOI culling: focused node plus first-order neighbors at full emphasis, remainder as reduced-emphasis context shell
- [ ] 6.2 Encode operational state (blocked, stale, awaiting-approval) using a non-colour channel in addition to colour
- [ ] 6.3 Encode urgency and dependency direction on edges
- [ ] 6.4 Assign stable numeric handles to addressable nodes and render them
- [ ] 6.5 Resolve spoken numeric handles ("open three") to the corresponding node
- [ ] 6.6 Add a persistent orientation cue and a return-to-default-orientation control
- [ ] 6.7 Verify DOI behavior at the current graph size (~27 nodes / 42 edges) and with a synthetic 200+ node graph

## 7. Voice spine

Delivers `vault-voice-spine`.

- [ ] 7.1 Pass a real `voice` param from `routes/home_routes.py` so the `audio` field stops being hardcoded standby (`cmd_center.py:1900`)
- [ ] 7.2 Derive the reported voice state from live voice subsystem state
- [ ] 7.3 Enforce the two-sentence spoken cap in `static/js/cmdCenterAudio.js`
- [ ] 7.4 Implement status-word emission (`recalling` / `inferencing` / `clarifying` / `correcting`) before substantive speech
- [ ] 7.5 Update `services/voice/vault_brief.py` `build_brief_script` to honor speak-vs-show: consequence and deadline spoken, exact values left to the screen
- [ ] 7.6 Implement the verification-text surface: what was heard plus interpreted action, with confirmation, before any external mutation
- [ ] 7.7 Confirm read-only voice commands do not require confirmation
- [ ] 7.8 Add the captions toggle (default off) for WCAG 1.2.4, with no verbatim transcript by default
- [ ] 7.9 Audit every voice affordance and add the missing keyboard twin for each
- [ ] 7.10 Tests: spoken length cap, status word ordering, verification-before-mutation, voice state accuracy

## 8. Domain intent

Delivers `vault-domain-intent`.

- [ ] 8.1 Extend `TAB_LAYOUT` (`cmdCenter.js:127-156`) so each domain declares a question, one primary verb, and an agent speech policy
- [ ] 8.2 Reject or flag any domain definition missing those three declarations
- [ ] 8.3 Render the active domain's question on the surface
- [ ] 8.4 Wire the speech policy into the agent so entering a domain changes what it volunteers
- [ ] 8.5 Present exactly one primary action per domain, matching its verb
- [ ] 8.6 Implement the empty-domain case: one statement instead of zero-valued counter panels
- [ ] 8.7 Reflect "nothing needs action" in the domain's navigation indicator
- [ ] 8.8 Update `docs/vault-cmd-center-component-atlas.md` and `CMD_COMPONENT_ATLAS` with domain-level intent
- [ ] 8.9 Tests: per-domain volunteered subject differs, single primary action, empty-domain collapse

## 9. Axis decision gate

Nothing here presumes an answer. Produces the evidence to decide, then stops.

- [ ] 9.1 Sketch A — domain axis: seven declared domains as the primary lens, per `vault-nav-model`'s existing filter-within-HUD requirement
- [ ] 9.2 Sketch B — state axis: `needs-approval` / `blocked` / `stale` / `running` as the primary lens, with domain as a secondary filter and a sphere region
- [ ] 9.3 Document the desktop compliance gap: `vault-nav-model` requires four canonical views on both breakpoints, desktop renders only the domain strip
- [ ] 9.4 Run both sketches against one week of real use and record which answers "what do I do next" faster
- [ ] 9.5 Record the decision, and open a `vault-nav-model` delta as separate work if the state axis wins

## 10. Verification and close-out

- [ ] 10.1 Run `python -m pytest tests/` and fix all failures
- [ ] 10.2 Run the project's type-check and lint if configured; if not configured, state that explicitly rather than claiming success
- [ ] 10.3 Count resting attention-layer regions on each of the seven domains and confirm the reduction against the ~40 baseline
- [ ] 10.4 Confirm no information present before this change has become unreachable
- [ ] 10.5 Confirm the legacy surface still renders with the preference flag off
- [ ] 10.6 Re-capture the seven domain screenshots and compare against `.tmp/cmd-center-tabs/` baselines
- [ ] 10.7 Run `openspec validate vault-audio-first-surface --strict`
