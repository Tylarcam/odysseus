# V.A.U.L.T. Reimagine — the canvas as operator story

**Question:** What does the live Story Canvas `vault-reimagine-1787098686` actually argue about Odysseus Command Center, and what should the next surface look like?
**Date:** August 19, 2026
**Audience:** Tylar / Odysseus product — people who will walk the board, not a status dump

---

## Executive summary (read first)

The live board is titled **V.A.U.L.T. Reimagine — 7 domain tabs annotated**. It is 18 nodes and 17 edges: four architecture cards across the top, seven annotated CMD Center screenshots in a `follows` sequence, each with a verdict card hanging below on a `supports` edge.

**Thesis:** the vault is a readout, not an operator. A domain tab swaps only the left and right rails. The center stage (globe, stage cards, glance chips, CEO quick-read, hero) is identical on all seven tabs. On RELAY the largest text on screen still says `PRIMARY DIRECTIVE — PROD`.

**Three hard facts from the canvas:**

1. About **40 text regions** compete at once, with no weighting; the same fact (attention count, documents, wire, agent runs, graph stats) is drawn up to four times.
2. Voice already binds both ways to the sphere (`_mapBriefHighlight` → `highlightNodes`; node click → `_speakNodeSummary`) but that seam is scoped to a ~30-second BRIEF ME script.
3. **MYCELIA** already has the pattern: six unambiguous verbs. The rest of the tabs report state.

**Implication:** do not invent a voice UI. Un-scope the one that exists. Sphere is the index; voice is the verb; the screen becomes confirmation and disambiguation — three weighted regions instead of forty.

**Next action:** walk the seven frames on the live canvas, then prototype one domain (RELAY or PROD) as TRUE + ACT + LISTENING, with rails behind “what else.”

---

## How the canvas is laid out

Open the live project: [Story Canvas — vault-reimagine-1787098686](http://localhost:7000/static/story-canvas/index.html?project=vault-reimagine-1787098686).

The board is a left-to-right film strip, not a hairball.

| Band | What you see |
|------|----------------|
| Top row (`y ≈ -260`) | Four text frames: PROBLEM, THE SEAM, PROPOSED, DOMAIN INTENT. Each `references` the CORE screenshot. |
| Middle row (`y ≈ 520`) | Seven **image frames**: annotated screenshots with numbered region boxes + a legend panel baked into the JPEG. Sequence 1–7. |
| Bottom row (`y ≈ 1320`) | Seven **verdict** text cards: `KEY · Verb: …` with target copy. |

Edges: `follows` chains CORE → MEM → PROD → COMMS → AGENCY → RELAY → MYCELIA. `supports` ties each shot to its verdict. Project JSON on disk: `.tmp/vault-reimagine-20260818/vault-reimagine.story.json` (id matches the URL). Server `GET /api/story-canvas/projects/...` 404s; the story is seeded in the browser (localStorage), which is why the live URL still loads the 18-node board.

Each screenshot frame is a CMD Center capture plus overlays: red / amber / green / cyan boxes on tab strip, left rail, center stage, right rail, footer, hero — numbered into a legend that states the region label and the critique.

---

## Act 1 — four architecture cards

### PROBLEM — the vault is a readout, not an operator

Seven domain tabs. Each swaps **only** the side rails. `TAB_LAYOUT` (`cmdCenter.js:127–156`) and `_buildHTML` (`3366–3386`) mount globe + five stage cards + glance chips + CEO quick-read + hero on every tab. A tab is a filter over peripheral vision, not a mode.

Three failures named on the card:

1. **Redundancy** — the same fact rendered up to 4×.
2. **Stats where decisions belong** — panels report state, never propose a move.
3. **Voice is a sidecar** — BRIEF ME is one-way TTS; Jarvis leaves the vault; the TTS STANDBY chip is hardcoded (`cmd_center.py:1900`).

### THE SEAM — voice ↔ sphere is already built

Highest-leverage finding. During BRIEF ME, `_mapBriefHighlight` (`cmdCenter.js:2944`) lights sphere nodes for the line being spoken via `highlightNodes` in `cmdCenterScene.js`. Clicking a sphere node calls `_speakNodeSummary` (`3452`) through `voiceRealtime`. Voice→sphere and sphere→voice both exist; they are scoped to scripted playback instead of being the permanent model. The canvas’s line: we are not building a voice interface from scratch — we are un-scoping one that is already there.

### PROPOSED — sphere is the index, voice is the verb

Screen becomes confirmation and disambiguation, not a dashboard with a speaker attached. Three text regions instead of forty:

- **DOMAIN RING** — 7 dots, lit by state. Replaces the tab strip.
- **THE SPHERE** — domain-lit and voice-lit. Unchanged, finally load-bearing.
- **TRUE:** one line. What is true in this domain right now.
- **ACT:** one button. The domain’s verb.
- **LISTENING** — mic state + waveform. Always present.

Rails are not deleted. They are demoted to on-demand (“what else”).

### DOMAIN INTENT — one question, one verb

`CMD_COMPONENT_ATLAS` documents a goal per **panel**, never per **domain**. The canvas writes the missing map:

| Domain | Question | Verb |
|--------|----------|------|
| CORE | What is on fire right now? | TRIAGE |
| MEM | What do I already know about it? | RECALL |
| PROD | What is the next move? | COMMIT |
| COMMS | Who is waiting on me? | REPLY |
| AGENCY | What did the agents produce? | REVIEW |
| RELAY | What is stuck between systems? | UNBLOCK |
| MYCELIA | What did the swarm learn? | HARVEST |

MYCELIA’s deck already proves the pattern. Promote it to all seven.

---

## Act 2 — seven annotated frames (the visual argument)

### Frame 1 — CORE · Verb: TRIAGE

Caption: *The baseline layout. Every other tab is a variation on this one.*

Annotations: 7 tabs swap only side rails; **KEEP** the sphere (the only element that shows how things relate, already voice-bound); four stacked left readouts (Vitals / Queue / Swarm / Docs) propose no action; Command Deck’s 12 unranked buttons are the only real verbs, buried bottom-right; BRIEF ME sits in the footer as a button; “10 DIRECTIVES” also appears in the glance chip, priority queue, and CEO quick-read — four times.

**Target on the verdict card:** one line of truth (“3 things need you, oldest is 4 days”), one act (Triage), sphere lit red on the offenders. Everything else on demand.

### Frame 2 — MEM · Verb: RECALL

Caption: *A notes feed, a stale brief, and a center stage that has no idea you switched tabs.*

A reverse-chronological note feed is not recall. Documents is the identical panel already on CORE’s left rail (`TAB_LAYOUT` 129 vs 134). Sphere unchanged. Hero still reads PRIMARY DIRECTIVE — PROD while you are standing in MEM.

**Target:** MEM is the tab where the sphere should be the **primary** input. Say a subject, the sphere reorients, focus card shows the strongest three connections. This is the tab that most wants to be spatial and is currently the most list-like.

### Frame 3 — PROD · Verb: COMMIT

Caption: *Ten tasks, ten identical START buttons. Ten equal choices is the same as no recommendation.*

The system knows priority, age, and due date, then hands ranking back to you. `'10 open / 0 blocked / 0 done / 10 live'` is a stat line, not a decision. Hero says PROD (correct for once) but now duplicates the right rail.

**Target:** ONE task, chosen and defended out loud (“Search as Code, because it has blocked two others for four days”). START becomes the single act. The other nine live behind “what else.” On this tab the sphere should collapse to that task’s dependency chain.

### Frame 4 — COMMS · Verb: REPLY

Caption: *11 unread, undifferentiated. The wire panel is empty and still holds a full column.*

A LinkedIn ping weighs the same as a human awaiting a reply. “Wire quiet” still occupies a full column. No tab states its purpose in the UI.

**Target:** “Two people are waiting on you. Longest is three days.” Sphere lights those two contact nodes. One act: Reply. The other nine emails are not on screen.

### Frame 5 — AGENCY · Verb: REVIEW

Caption: *Third rendering of the same `agent_activity[]`. The right rail is all zeros and still full height.*

Agent runs appear on CORE (Swarm Activity), here (Agency Board), and MYCELIA again. `'0 ready / 0 review / IDLE'` is a full panel to report nothing happened. Audio I/O appears on CORE and AGENCY only, with no stated reason. Nothing in the center stage tells you this tab is a review queue.

**Target:** if zero items need review, say one sentence and give the space back — better, dim its dot in the domain ring so you never open it.

### Frame 6 — RELAY · Verb: UNBLOCK

Caption: *The clearest case in the build: nine numbers, eight of them zero, one that matters styled identically.*

Right rail: Waiting 0, Stuck 0, In flight 0, Issued(7d) 3, Completed 2, Failed 1, Open 0, Close rate 67%, IDLE. “Failed 1” is the only actionable number and looks exactly like “Close rate 67%.” The canvas names this **alarm flooding**. You are on RELAY; the biggest text still says PRIMARY DIRECTIVE — PROD. Relay is edges between systems — a graph problem — and the graph shows something unrelated.

**Target:** “One handoff failed. Want to see it?” — and nothing else until you say yes.

### Frame 7 — MYCELIA · Verb: HARVEST

Caption: *The best tab in the build — six real verbs — and it still prints its graph stats twice.*

Mycelia Deck: CEO Brief, Run COO Plan, Dispatch Forager, Send to Research, Dispatch Scout, All Agents. The only place the vault feels like an operator console. Swarm Activity is the third copy of `agent_activity[]`. `27 nodes / 42 edges` is printed twice in text; the sphere can show that without words. Hero still pinned to PROD — seven tabs, one hero, wrong six times.

**Target:** promote this deck’s model everywhere. Every domain gets its verbs.

---

## Implications

If the canvas is right, the next CMD Center is not “fewer panels.” It is a **mode** per domain (question + verb), a **permanent** voice↔sphere loop, and a screen that confirms rather than catalogs.

**Risks:** demoting rails to “what else” can hide diagnostics operators still need on bad days; dimming an empty AGENCY ring can hide a silent agent failure; one TRUE line can be wrong if ranking is naive.

**Open questions the board does not close:** which domain to prototype first (RELAY is the clearest failure; MYCELIA is the clearest success); how LISTENING coexists with BRIEF ME without another sidecar; whether the domain ring replaces tabs in one cut or behind a flag.

Walk the board, then ship one TRUE / ACT / LISTENING slice.

---

## Sources

1. [Live Story Canvas — vault-reimagine-1787098686](http://localhost:7000/static/story-canvas/index.html?project=vault-reimagine-1787098686)
2. On-disk project JSON: `C:/Users/tylar/code/odysseus/.tmp/vault-reimagine-20260818/vault-reimagine.story.json` (id `vault-reimagine-1787098686`, title matching the live board)
3. Builder: `.tmp/vault-reimagine-20260818/build_canvas.py` (annotated 7-tab screenshots + architecture nodes)
4. Problem statement: `.tmp/vault-reimagine-20260818/problem-statement.md`
5. Code cited on the cards: `static/js/cmdCenter.js` (`TAB_LAYOUT`, `_buildHTML`, `_mapBriefHighlight`, `_speakNodeSummary`), `cmdCenterScene.js` (`highlightNodes`), `cmd_center.py:1900`
