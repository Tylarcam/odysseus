## Context

V.A.U.L.T. is a client-rendered HUD. `services/home/cmd_center.py` aggregates one large payload;
`static/js/cmdCenter.js` builds all HTML from it. Seven domain tabs (CORE, MEM, PROD, COMMS, AGENCY,
RELAY, MYCELIA) swap left and right rail panels via `TAB_LAYOUT` (`cmdCenter.js:127-156`), while
`_buildHTML` (`:3366-3386`) mounts the center stage — globe, five stage cards, glance chips, CEO
quick-read, hero directive — **unconditionally and identically on all seven tabs**.

The observable consequence: on the RELAY tab the largest, brightest, most central element still reads
`PRIMARY DIRECTIVE — PROD`. A domain tab is a filter over peripheral vision, not a mode.

### What was already tried

`vault-cmd-center-focus-orchestration` (complete, 37/37) diagnosed a near-identical problem — "a single
handoff or job can compete for attention in up to 8 places at once" — and shipped `vault-signal-priority`
to fix it. That fix works, but its scope was deliberately narrow in two ways that leave the current
problem intact:

1. It governs only `commands`, `suggested_commands`, and `stage_cards`.
2. It explicitly requires that "Status Pills, `branch_health` rows, and the AI Wire ticker SHALL
   continue to reflect every relevant item," reasoning that they are glanceable status rather than
   action surfaces.

That reasoning is sound for *CTA* duplication and wrong for *salience* load. A glanceable surface that
restates every item as text is not glanceable. This change keeps the registry and extends it.

`cmd-center-active-systems` (complete, 43/43) specified each domain's rails, including `relay_stats`
close-rate reporting. Nothing there was a mistake. The problem is emergent: individually correct
requirements summing to ~40 simultaneous competing regions.

### Constraints

- **The sphere stays.** Non-negotiable operator constraint. It is also the only element on screen that
  shows how things *relate* rather than listing what *exists*.
- **The information sphere's data and relationships stay.** The operator explicitly does not want the
  surfaced detail removed — only re-hosted and re-ranked.
- **No new dependencies** without approval (workspace rule).
- **`cmdCenter.js` is 4300 LOC.** Step 0 rule applies: dead-code removal ships as its own commit before
  structural work.
- **The organizing axis is undecided.** Design must not presume domain or state.

### Evidence base

Full research report: `/api/research/report/rp-vault-audio-surface-20260818` (55 sources). The three
load-bearing external findings:

| Finding | Source |
|---|---|
| ~1 alarm/10min acceptable; >10/10min is a defined *alarm flood* | ISA-18.2, EEMUA 191 |
| Voice is efficient input / inefficient output; screen is the reverse | NN/g |
| Full graph is decorative, local graph is useful; degrades ~200 nodes | Obsidian community consensus |

## Goals / Non-Goals

**Goals:**

- Reduce resting salience load from ~40 competing regions toward ~3, without making any current
  information unreachable.
- Make the voice↔sphere binding that already exists (`_mapBriefHighlight`, `_speakNodeSummary`) the
  permanent interaction model instead of a 30-second scripted playback.
- Give each domain a stated purpose and one primary verb, so "what am I supposed to do here" is
  answered on screen.
- Establish a durable rule (not a one-time cleanup) that prevents density regrowth, since the previous
  density fix regressed by addition.
- Keep every axis-dependent decision out of the critical path.

**Non-Goals:**

- Rebuilding navigation chrome. Gated on the axis decision.
- Removing the sphere, its data, or its relationship rendering.
- Replacing Jarvis / `voiceRealtime.js` with a new voice stack. This change re-scopes existing surfaces.
- Restoring `routes/story_canvas_routes.py` (0 bytes). Unrelated, tracked separately.
- Making voice the *only* input. Every voice affordance gets a keyboard twin, deliberately.
- Mobile redesign. The existing 4-tab model must stay coherent, nothing more.

## Decisions

### D1 — Rationalize at the server, filter at the client

Salience is decided in `build_cmd_center()` by emitting `consequence`, `response_time`,
`operator_action`, and a derived `salience_tier`; `cmdCenter.js` renders by tier.

*Why:* ranking requires data the client does not have (age, dependency depth, history). Alternative
considered — client-side heuristics — was rejected because it would drift from the server's own
`priority_queue` ranking and produce two disagreeing notions of urgency. This also mirrors the
established precedent: `vault-signal-priority` already computes `primary_slot` server-side.

*Consequence:* if the server cannot supply an `operator_action` for an item, the item is by definition
not an alarm. That is the forcing function — it makes the rule impossible to satisfy by restyling.

### D2 — Reclassify, do not delete

Items failing the rationalization test move to on-demand detail, reachable in one phrase or one
keystroke. Nothing is removed from the payload.

*Why:* the operator's stated constraint is that the surfaced detail must remain. ISA-18.2 prescribes
exactly this remedy — reclassify alarms as events "to be recorded by the automation system for later
review, instead of as items requiring immediate operator attention." Alternative considered — deleting
low-value panels — violates the constraint and destroys information.

*Worked example:* `relay_stats` keeps computing all nine values. `Failed 1` (consequence: blocked
downstream work; action: unblock) stays in the attention layer. `Close rate 67%` has no operator action
and becomes detail.

### D3 — At most 3 salience tiers, ~5% top tier

ISA-18.2 recommends no more than three or four priorities, targeting ~80% low / ~15% medium / ~5% high.

*Why:* an unbounded tier count reproduces the current problem with extra vocabulary. The distribution
target is what makes the top tier mean something. Alternative considered — a continuous urgency score —
was rejected because a continuous scale cannot be rendered as distinguishable visual weight, and
operators cannot act on 0.73 vs 0.71.

### D4 — Focus is a first-class object with provenance, not a hover state

```
focus = {
  focused_entity, focused_edge,
  focus_source: voice | click | agent | search,
  focus_confidence, focus_timestamp
}
```

*Why:* `focus_source` is the field that makes correct behavior possible when the operator clicks away
mid-sentence — the agent must know whether it or the human established the current referent. Without
provenance, voice and pointer fight over the same variable. Deictic reference ("open that one") only
works when language and spatial state are grounded concurrently; this is the Put-That-There lineage.

Alternative considered — reusing the existing transient highlight state in `cmdCenterScene.js` — was
rejected because it has no provenance, no confidence, and no lifetime, and is reset by every brief
playback.

### D5 — The sphere becomes a degree-of-interest view

Render the focused node, its first-order neighbors, and a faint context shell. Encode operational state
(blocked / stale / awaiting-approval) in node appearance, never by colour alone. Give addressable nodes
numeric handles.

*Why:* the community verdict on full-graph views is consistent and specific — "a topological map of your
connections, not an operational view of your knowledge work. It does not show note status. It does not
show priorities." DOI culling is what converts the sphere from proof-that-a-graph-exists into
where-attention-is-owed. Numeric handles come from Echo Show: numbers "provide unique and efficient
verbal handles," so "open three" is unambiguous where "open the Salesforce one" is not.

Alternative considered — keeping the full sphere and adding a separate focus panel — was rejected
because it adds a region rather than making the existing one load-bearing, and the sphere is the surface
the operator asked to preserve.

### D6 — Verification text, not a transcript

Render *what was heard* and *what is about to be done* before any external mutation. Do not render a
verbatim scrolling narration. Captions available behind an explicit toggle.

*Why:* Amazon's rule is direct — "Don't include long texts that repeat exactly what Alexa is saying" —
and duplicating narration triggers redundancy / split-attention effects. But WCAG 1.2.4 requires live
captions, and both ChatGPT Voice and Gemini Live shipped optional captions rather than omitting text. So
the question is *which* text. Verification text is the transcript feature with evidence behind it; the
scrolling transcript is the one with evidence against it.

*Caveat carried into risks:* the redundancy evidence comes from novice-learner experiments, and
expertise-reversal work suggests it weakens for experts. A single power user is where that literature
transfers worst. This is a strong default with an escape hatch, not a law.

### D7 — 1–2 spoken sentences per turn, with a status word first

Cap spoken output. Emit a single status word (`recalling`, `inferencing`, `clarifying`, `correcting`)
the instant prefill ends.

*Why:* long TTS is where voice stacks break in practice ("anything more than a couple sentences
basically dies"), and Alexa+ is being abandoned by power users specifically for "annoying chattiness."
The status word masks latency at ~1.5s perceived and, critically, tells the operator the system heard
them — the exact uncertainty that sank Rabbit R1.

### D8 — Domain intent lives in `TAB_LAYOUT`, as a speech policy

`TAB_LAYOUT` currently maps a domain to a rail list. It gains a question, a verb, and an agent speech
policy describing what the agent volunteers on entry.

*Why:* this is the cheapest possible differentiation of the seven tabs — seven system prompts do more
work than any panel rearrangement, and they are axis-independent (a speech policy attaches equally well
to a state bucket). It also directly targets the operator's complaint, which was about *context*, not
layout.

### D9 — Keyboard twin for every voice affordance

*Why:* the R1 and Humane post-mortems share one root cause — voice as the only recovery path. A desktop
operator has a keyboard within reach, and practitioners are blunt that "typing is always still faster
and more accurate" for precise work. `vault-keyboard-shortcuts` already established the pattern.

### D10 — Axis decision is a gate, resolved by prototype

Phases 1–4 are axis-independent. The domain-vs-state decision is made after both sketches exist and
have been compared against real daily use.

*Why:* the operator is explicitly undecided, and the evidence genuinely conflicts — practitioners
organize agent work by state, while `vault-nav-model` already established domain-as-filter here.
Deciding on paper would be guessing; deciding after Phases 1–4 costs nothing because none of that work
depends on the answer.

## Risks / Trade-offs

- **[The single focus card becomes the old 40 regions arriving one at a time]** → Ranked and
  rate-limited queue, plus instrumentation on approval volume and override rate. The named failure modes
  for ambient surfaces are "notification sludge" and rubber-stamped approvals; if override rate
  approaches zero, review has become a formality and the ranking is wrong.
- **[Density regrows by addition, exactly as it did after `vault-signal-priority`]** → The
  rationalization test is a spec-level gate, not a cleanup pass: a new panel cannot enter the attention
  layer without a consequence and an operator action. This is the primary defense and the main reason
  this is a capability rather than a refactor.
- **[The 3D sphere has no research support as a voice-first anchor]** → Logged as an explicit design
  assumption. The general literature leans against 3D layouts (occlusion, unstable spatial memory under
  rotation), and all supporting graph-visualization evidence comes from mouse-driven 2D desktop tools.
  Mitigations: DOI culling and a stable orientation cue. This is a fixed constraint, so the honest
  position is to test it, not to argue it away.
- **[Voice bandwidth is genuinely worse than reading]** → ~150 wpm speech vs ~250–300 wpm silent
  reading, serial access, no skimming, evaporates. Mitigated by the speak-vs-show split (voice never
  carries lists or exact values) and keyboard twins. Accepted rather than solved.
- **[Removing text from passive surfaces could hide real state]** → This is the explicit reversal of a
  requirement in `vault-signal-priority`, so it deserves the scrutiny. Mitigation: passive surfaces
  collapse to a count plus sphere state — the state remains visible, only its textual restatement is
  removed, and `priority_queue` remains unfiltered so nothing becomes undiscoverable.
- **[Over-rotating on voice purity]** → NN/g warns that "deliberately handicapping the functionality of
  a screen in the name of 'pure' voice interaction unnecessarily limits the usefulness of the device."
  The 3-region target is a direction, not a scoring metric; the fire rail is a deliberate concession.
- **[Trade-off accepted]** Two disclosure levels means some information is now two steps away that was
  previously zero steps away. Nielsen's counter is that "the very fact that something appears on the
  initial display tells users that it's important" — with 40 co-equal regions the surface currently
  communicates that nothing is.

## Migration Plan

1. **Step 0 commit** — dead code, unused props/exports, debug logs removed from `cmdCenter.js` and
   `cmd_center.py`. No behavior change. Separate commit per workspace rule.
2. **Additive server phase** — emit rationalization fields alongside existing ones. Payload is
   backward-compatible; nothing renders differently yet. Verifiable via `tests/test_home_dashboard.py`.
3. **Client tier filtering behind a flag** — reuse the existing `odysseus-cmd-center-visibility`
   preference mechanism to gate the new rendering, so the old surface remains one toggle away for
   direct comparison.
4. **Focus protocol** — introduce the focus object, then re-point `_mapBriefHighlight` and
   `_speakNodeSummary` at it. BRIEF ME continues working throughout; it becomes one consumer instead of
   the owner.
5. **Rollback** — Phases 2 and 3 are independently revertable (additive fields; a preference flag).
   Phase 4 is the first non-trivial revert and lands last among the axis-independent work.

## Open Questions

1. **Domain axis or state axis?** Gated deliberately. See D10 and Task group 5.
2. **How much verification text for an expert user?** D6 sets a default; the expertise-reversal
   literature suggests a single power user may tolerate or want more. Needs use, not analysis.
3. **Does the sphere hold up as a voice anchor at real node counts?** Degradation is reported ~200
   nodes; the current graph is ~27 nodes / 42 edges, so this is not yet binding but will become so.
4. **What is the right rate limit for the focus queue?** ISA-18.2's ~1 item per 10 minutes is derived
   from process-control operators, not knowledge work. The order of magnitude is likely transferable;
   the exact figure is not.
5. **Should the fire rail be 3 items or fewer?** Chosen as `Now / Next / Blocked`, but ISA-18.2's ~5%
   top-tier target may imply fewer at low total volume.
