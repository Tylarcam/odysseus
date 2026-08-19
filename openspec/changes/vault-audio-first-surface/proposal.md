## Why

V.A.U.L.T. presents roughly 40 competing text regions simultaneously and permanently. ISA-18.2 puts a
single operator's sustainable limit at ~1 alarm per 10 minutes, and EEMUA 191 defines an *alarm flood* —
a named emergency condition — as more than 10 alarms per 10 minutes. The vault's resting state is
therefore ~4× the flood threshold, which is why the operator reports "too much text and not clear
context for what is supposed to be done on each domain tab."

No individual panel is wrong. `cmd-center-relay-system` deliberately specified a close-rate view;
`cmd-center-active-systems` deliberately gave each domain its own rails. Each requirement was
individually correct and the aggregate is unusable. `vault-signal-priority` already fixed CTA
duplication, but it explicitly scoped itself to `commands` / `suggested_commands` / `stage_cards` and
declared passive status surfaces "exempt from deduplication" — so panel-level redundancy and total
salience load were never addressed. This change addresses the aggregate.

Two facts make now the right time. First, the interaction model the operator wants already exists in
the codebase but is scoped too narrowly: `_mapBriefHighlight` (`cmdCenter.js:2944`) lights sphere nodes
in sync with spoken lines, and `_speakNodeSummary` (`:3452`) speaks a node on click — bidirectional
voice↔sphere binding, confined to a 30-second scripted BRIEF ME playback. Second, the established
guidance is unambiguous about why the current split fails: voice is an efficient *input* modality and an
inefficient *output* modality, and the screen is the reverse. The vault has this inverted — it reads
lists aloud while displaying forty things nobody asked for.

## What Changes

- **Rationalize the attention layer.** Every item competing for salience must carry a `consequence`, a
  `response_time`, and an `operator_action`. Items failing that test are reclassified as
  log/detail — reachable, but not resting salience. At most 3 salience tiers, with roughly 5% of
  surfaced items eligible for the top tier. The RELAY rail (`Waiting 0 · Stuck 0 · In flight 0 ·
  Issued 3 · Completed 2 · Failed 1 · Open 0 · Close rate 67% · IDLE`) is the canonical worked example:
  eight of those nine numbers become on-demand detail; `Failed 1` becomes the only alarm.
- **Promote the voice↔sphere binding to the permanent interaction model.** Introduce a first-class
  focus object (`focused_entity`, `focused_edge`, `focus_source`, `focus_confidence`,
  `focus_timestamp`) as the shared referent between speech and the sphere. `focus_source` is what lets
  the agent behave correctly when the operator clicks away mid-sentence.
- **Scope the sphere to a degree-of-interest view** — focused node, first-order neighbors, faint
  context shell — and encode operational state (blocked / stale / awaiting-approval) in node
  appearance. Addressable nodes get numeric verbal handles so "open three" is unambiguous. The sphere
  is retained unchanged as a concept and becomes load-bearing rather than decorative.
- **Establish a speak-vs-show contract.** Voice carries intent, verdict, consequence, deadline, and
  confirmation requests, capped at 1–2 sentences per turn. The screen carries state, comparison, exact
  values (names, dates, IDs, amounts), and anything requiring re-reading. A status word (`recalling`,
  `inferencing`) emits the instant prefill ends so the operator never waits in silence.
- **Ship verification text, not a transcript.** No verbatim scrolling narration (redundancy /
  split-attention, and Amazon's explicit rule against repeating spoken text on screen). Instead render
  *what was heard* and *what is about to be done*, before any external mutation. Captions remain
  available as an explicit toggle for WCAG 1.2.4.
- **Every voice affordance gets a keyboard twin.** The Rabbit R1 / Humane failure pattern was voice as
  the only recovery path; a desktop operator already has the better input device on the desk.
- **Each domain declares its intent.** A domain gains a stated question, one primary verb, and an agent
  speech policy governing what the agent volunteers on entry. `CMD_COMPONENT_ATLAS` documents a goal
  per *panel* today but nothing per *domain*, which is the direct cause of "not clear context for what
  is supposed to be done on each domain tab."
- **Cap disclosure depth at 2 levels** (sphere → focus card → detail). Designs beyond two levels have
  low usability.
- **BREAKING (internal only)**: payload items gain `consequence` / `response_time` /
  `operator_action` / `salience_tier`. Rail renderers that assumed every field is render-worthy must
  switch to tier-filtered rendering.

### Deferred decision (explicit gate)

The operator has not yet chosen the organizing axis, and this change does **not** presume one. Research
found that practitioners organizing agent work converge on *state* (needs-approval / blocked / stale /
running), not subject domain, while `vault-nav-model` already established domain tabs as a filter
within `HUD`. Phases 1–3 below are axis-independent and deliver most of the density reduction. The axis
decision is a gate before the navigation chrome is rebuilt, and Task group 5 produces both sketches for
comparison against real daily use rather than resolving it on paper.

## Capabilities

### New Capabilities

- `vault-attention-rationalization`: the ISA-18.2-derived test that decides whether an item may occupy
  the attention layer at all — requires consequence, response time, and a distinct operator action —
  plus salience tier limits, tier distribution targets, and the reclassification rule that moves
  non-qualifying metrics to on-demand detail. Also caps progressive-disclosure depth at 2 levels.
- `vault-focus-protocol`: the first-class focus object and the mutual-reference contract between voice
  and the sphere, including the degree-of-interest rendering it drives (focused node + first-order
  neighbors + context shell), operational-state encoding, and numeric verbal handles for addressable
  nodes.
- `vault-voice-spine`: the speak-vs-show division of labor, the spoken-length cap, status-word latency
  masking, verification-text-before-mutation (explicitly not a verbatim transcript), optional captions
  for WCAG 1.2.4, and the keyboard-twin requirement for every voice affordance.
- `vault-domain-intent`: per-domain declared question, primary verb, and agent speech policy, so
  entering a domain changes what the agent volunteers rather than only which rails render.

### Modified Capabilities

- `vault-signal-priority`: extend the registry beyond `commands` / `suggested_commands` /
  `stage_cards` to rail panels, and modify the "passive status indicators are exempt from
  deduplication" requirement so those surfaces stay within a salience budget — collapsing to a count
  plus sphere state rather than restating every item as text.

`vault-nav-model` is deliberately **not** modified. It already requires that domain be "a secondary lens
on HUD, not a competing nav axis," which is compatible with this change; the per-domain question, verb,
and speech policy land in the new `vault-domain-intent` capability instead. If the axis gate (below)
resolves toward a state-based axis, that will require its own `vault-nav-model` delta as separate work.

Worth flagging separately: `vault-nav-model` requires four canonical top-level views (`HUD` / `Queue` /
`Commands` / `Wire`) on **both** breakpoints, but desktop currently renders only the seven-domain strip
in `header.cmd-topbar > nav#cmd-domain-tabs` with no visible four-view control. That gap predates this
change and is not in scope here, but it means the axis question is partly a compliance question rather
than purely a new decision.

## Impact

- `services/home/cmd_center.py` (1875 LOC) — emit `consequence` / `response_time` /
  `operator_action` / `salience_tier` per surfaced item; extend the signal registry to rail panels;
  `_build_relay_stats` (:689) demoted to on-demand detail; `voice` param actually passed so the
  `audio` field stops being hardcoded standby (:1900).
- `static/js/cmdCenter.js` (4300 LOC) — tier-filtered rail rendering; `_mapBriefHighlight` (:2944) and
  `_speakNodeSummary` (:3452) promoted out of brief-playback scope into the focus protocol;
  `TAB_LAYOUT` (:127-156) gains intent + speech policy; de-duplicate Documents (CORE left / MEM right),
  AI Wire (4 domains), agent activity (3 renderings), MYCELIA graph stats (2 panels), and the
  hero/glance/quick-read attention count (4 renderings). **Per the Step 0 rule, dead-code removal in
  this file lands as its own commit before structural work.**
- `static/js/cmdCenterScene.js` (1158 LOC) — degree-of-interest culling, operational-state node
  encoding, numeric handles, stable orientation cue.
- `static/js/cmdCenterAudio.js` (230 LOC) — spoken-length cap, status-word emission; BRIEF ME becomes
  one consumer of the voice spine rather than the only audio path.
- `services/voice/vault_brief.py` (504 LOC), `routes/voice_routes.py` — brief script honors the
  speak-vs-show contract; vault-brief context includes the focus object.
- `static/js/voiceRealtime.js`, `voiceChat.js`, `voiceKeyboardPtt.js` — Jarvis stops being a separate
  destination; keyboard twins registered.
- `docs/vault-cmd-center-component-atlas.md` — mirror of `CMD_COMPONENT_ATLAS`; goes stale immediately
  otherwise.
- Tests: `tests/test_home_dashboard.py` (rationalization fields, tier limits, registry extension,
  relay stat demotion) plus frontend smoke checks for focus protocol and keyboard twins.
- **Risk carried forward, not resolved**: there is no published research on a 3D node sphere as a
  voice-first anchor, and the general literature leans against 3D layouts (occlusion, unstable spatial
  memory under rotation). The sphere is a fixed constraint here. Mitigations are DOI culling and a
  stable orientation cue; the assumption is logged in `design.md` to be tested rather than inherited.
- **Out of scope**: rebuilding the navigation chrome (gated on the axis decision); restoring
  `routes/story_canvas_routes.py` (0 bytes, unrelated); mobile-specific layout beyond keeping the
  existing 4-tab model coherent.
