# V.A.U.L.T. × CEO Transcript Insights

> Synthesis of CEO brief workflows, YouTube transcript docs, morning-brief ops, and executive-comms patterns — translated into **needle-moving** V.A.U.L.T. features not yet built.
>
> **Companion:** [`docs/vault-cmd-center-prd.md`](vault-cmd-center-prd.md) (engineering completion PRD)

---

## Sources reviewed

| Source | Path | Core idea |
|--------|------|-----------|
| YouTube CEO Brief skill | `data/skills/general/youtube-ceo-brief/SKILL.md` | Video URL → transcript → decision-ready brief w/ playbook (S/M/L) |
| Fable / Mythos transcript | `Fable5_yt_trancript.md` | Multi-agent orchestration, morning PR queue, remote agent ops, ambition bar |
| Hermes + Ollama transcript | `hermes_agent_yt_transcript.md` | Private OS, three compute modes, unified memory/goals/skills |
| Ras Morning Brief prompt | `prompts/ras-morning-brief.md` | ONE human action, HUMAN/DELEGATE/DEFER buckets, quick-read strip |
| Executive brief template | `prompts/executive-brief-template.md` | Board-ready meeting → actions w/ delegation class |
| Work pattern audit | `prompts/work-pattern-audit.md` | Needle-movers vs busywork, operating rhythm from evidence |
| CEO follow-up comms | `chat2workflow_email_followups.md` | CEO **scans** (~45s); evidence-linked; every word earns its place |
| MorningAI prep | `docs/morningai-one-pager.md`, `docs/morningai-screening-prep.md` | Expansion GTM, post-call briefs, account 5–10x playbook |
| Olivia exec brief | `docs/olivia-local-model-executive-brief/solution-brief.md` | Privacy-first brief pipeline on local model |
| Daily digest example | `chat2workflow_email_followups.md` (MeritFirst/MorningAI stale leads) | Stale + fit scoring drives urgency |

**Not CEO transcript but referenced in HUD map:** `docs/stanford-ma-transcript.md` (credentials — out of scope for vault UX).

---

## Cross-cutting themes (what “move the needle” means in these docs)

1. **Scan, don’t study** — Busy executives (Chris-type CEOs) need ≤45s read: structure upfront, one line per point, proof links not paragraphs.
2. **One human action** — Ras brief: exactly one “Do This Today”; everything else delegate, defer, or drop.
3. **Evidence before ask** — Will-letter pattern: shared moment → proof → ask last.
4. **Verb-first playbook** — CEO brief skill: actions executable in **days**, effort S/M/L, edges vs wedges.
5. **Agent orchestration as ops** — Fable: ranked queues, agents review agents, babysitting loops, cron heartbeats, phone kickoff.
6. **Private vs cloud routing** — Hermes: vault mode for sensitive IP; cloud for quality; local for $0 24/7 agents.
7. **Expansion > net-new logos** — MorningAI: nail current customers, 5–10x existing accounts — maps to Agency branch semantics.
8. **Stale = urgency** — Job pipeline digest: fit 4–5/5 + days stale = top of queue (revenue clock).

---

## V.A.U.L.T. features to add (not in current build or PRD)

These extend the situation room from **dashboard** to **daily operating system**.

### Tier A — Highest needle (revenue + CEO scan)

| ID | Feature | Inspired by | Vault placement | Behavior |
|----|---------|-------------|-----------------|----------|
| **T-A1** | **CEO Quick Read strip** | Ras `Quick read` + chat2workflow scan rule | Under hero (5 bullets max) | Auto-filled: Do today · Delegated · Calendar · Email · Blocked — each one line, clickable |
| **T-A2** | **Single HUMAN slot** | Ras Phase 2–4 | Hero OR #1 in priority queue w/ distinct styling | Exactly one item Tylar must do today; scoring: revenue/deadline > handoff > job apply |
| **T-A3** | **Stale heat on Agency rows** | Daily digest + job pipeline | Priority queue + job panel | Show `9d stale · fit 5/5` on jobs; sort boost when stale × fit high |
| **T-A4** | **One-click CEO follow-up** | chat2workflow + follow-up-email skill | Agency row / Morning card | From queue → draft follow-up (evidence-linked template) → email library draft, not generic Notes |
| **T-A5** | **Needle vs Spin tag** | work-pattern-audit | Each priority row | Badge: `NEEDLE` (revenue/deadline/5-fit job) vs `SPIN` (maintenance); filter toggle |

### Tier B — Intel & learning loop

| ID | Feature | Inspired by | Vault placement | Behavior |
|----|---------|-------------|-----------------|----------|
| **T-B1** | **Intel Ingest (video URL)** | youtube-ceo-brief skill | Command deck + float card “Intel Ingest” | Paste URL → `transcribe_video` → CEO brief doc + wire entry + optional playbook rows in suggested commands |
| **T-B2** | **Playbook panel** | CEO brief `\| # \| Action \| Effort \| Why now \|` | Right rail tab or modal | Latest CEO brief’s playbook table; click row → create handoff or note |
| **T-B3** | **Edges / Wedges chip** | CEO brief structure | Float card or hero footnote | From latest intel brief: 1-line “where this breaks” + 1-line “asymmetric bet” |
| **T-B4** | **Maturity / hype gap** | CEO brief Technology section | AI Wire prefix on intel items | Tag intel lines: `PROVEN` vs `CLAIMED` from brief extractor |

### Tier C — Agent orchestration (Fable patterns)

| ID | Feature | Inspired by | Vault placement | Behavior |
|----|---------|-------------|-----------------|----------|
| **T-C1** | **IN_FLIGHT lane** | Ras `IN_FLIGHT` + Fable babysitting | Wire section or sub-panel | Handoffs in_progress + running scheduled tasks; distinct from “needs attention” |
| **T-C2** | **Delegate from queue** | Ras Phase 3 | Priority row action menu | `→ Cursor` / `→ Claude` creates handoff packet w/ real doc id + pickup line |
| **T-C3** | **Agent heartbeat strip** | Fable cron + task scheduler | Prod pill tooltip / wire | Show next scheduled task fire + last run status (Morning Brew, job pipeline, Ras brief) |
| **T-C4** | **Ranked review queue** | Fable morning PR ranking | Future: git integration | Ranked “easiest merge / highest impact” PRs or handoff docs — **defer until git API**; placeholder: ranked **documents** or **handoffs** by age + type |
| **T-C5** | **HTML plan review links** | Fable plan URLs | Handoff cards | Handoffs with review HTML open in phone-friendly viewer (document preview URL) |

### Tier D — Privacy & compute modes (Hermes / Olivia)

| ID | Feature | Inspired by | Vault placement | Behavior |
|----|---------|-------------|-----------------|----------|
| **T-D1** | **Compute mode indicator** | Hermes vault/connected/cloud | Top bar or Audio I/O | `PRIVATE` (local model) · `CONNECTED` · `CLOUD` — reflects current chat model + voice gateway |
| **T-D2** | **Sensitive brief route** | Olivia solution brief | Intel ingest flow | Toggle: “brief on local model only” when ingesting confidential notes |
| **T-D3** | **Delegation class on actions** | executive-brief-template | Playbook + delegate flow | Tag actions: Local / Staff / Cursor / Claude / External + redaction hint |

### Tier E — Morning ritual (merged Ras + vault PRD G-17)

| ID | Feature | Inspired by | Behavior |
|----|---------|-------------|----------|
| **T-E1** | **Start Day flow** | Ras phases 1→5 + vault morning mode | First open/day: sync → run scoring → surface ONE human → pre-fill suggested commands → optional auto-run Ras brief task |
| **T-E2** | **Post-call brief hook** | MorningAI one-pager (“Claude → post-call briefs”) | After calendar event w/ “screen” label → prompt to ingest notes → CEO scan summary |
| **T-E3** | **Expansion radar** | MorningAI 5–10x | Agency card when no jobs: show top accounts from CRM notes (keyword: expansion, QBR) |

### Tier F — Work pattern audit (monthly, surfaced in vault)

| ID | Feature | Inspired by | Behavior |
|----|---------|-------------|----------|
| **T-F1** | **Needle : busywork ratio** | work-pattern-audit | Monthly widget in vault or hero footnote: “Last 30d: 35% needle / 65% spin” |
| **T-F2** | **Repeated question → skill** | work-pattern-audit §B | Wire suggestion: “You asked X 12× — save as skill?” |
| **T-F3** | **Operating rhythm table** | work-pattern-audit §2 | Settings/vault link: proposed crons not yet enabled (one-click enable task) |

---

## Mapping to existing PRD gaps

| PRD gap | Transcript insight upgrade |
|---------|---------------------------|
| G-01 Job panel read-only | Add T-A3 stale heat + T-A4 follow-up + open apply package |
| G-17 Morning ritual | Expand to T-E1 Start Day (Ras phases baked in) |
| G-11 Live updates | T-C3 heartbeat strip can poll before full SSE |
| Hero explain | T-A1 Quick Read replaces long prose |
| Wire filters | Add `NEEDLE` / `INTEL` / `IN_FLIGHT` filter chips |
| suggested_commands | Feed from latest CEO brief playbook (T-B2) |

---

## Recommended vault layout (target state)

```
┌─ TOP: brand · branch pills · compute mode · clock · sync · − ─┐
├─ QUICK READ (5 bullets) ────────────────────────────────────────┤
│ LEFT          │ CENTER (3D)              │ RIGHT               │
│ Vitals        │ constellation            │ Suggested (+ playbook)│
│ Priority Q    │ float cards              │ Command deck        │
│ (+ NEEDLE)    │ HERO + 1 HUMAN           │ Audio / mode        │
│ Documents     │ CEO scan title           │ AI Wire (+ filters) │
└───────────────┴──────────────────────────┴─────────────────────┘
```

---

## Priority implementation order

> **Phases 5–8 in this doc are post-PRD, not the next thing the implementer should pick up.** The PRD (Phases 1–4) is authoritative; finish PRD Phases 3 and 4 first. The Waves below are what comes *after* the PRD ships. Renamed from "Phase 5–8" to avoid collision with PRD numbering — see `docs/vault-prd-cross-reference.md` §1 for the full rationale.

| Wave | Items | Outcome |
|------|-------|---------|
| **Wave 1** | T-A1, T-A2, T-A3, T-A5 | Vault answers “what do I do today?” in 5 seconds |
| **Wave 2** | T-A4, T-B1, T-B2, T-E1 | Revenue loop: stale jobs → follow-up; video → playbook |
| **Wave 3** | T-C1, T-C2, T-C3, T-D1 | Agent OS: delegate + heartbeat + compute mode |
| **Wave 4** | T-B3, T-B4, T-E2, T-F1 | Intel quality + monthly pattern feedback |

---

## Acceptance criteria (CEO-transcript tier)

- [ ] Hero + Quick Read readable in **≤45 seconds** (manual test)
- [ ] Exactly **one** HUMAN item marked; rest tagged DELEGATE/DEFER/IN_FLIGHT
- [ ] Stale 5/5 job appears above stale 3/5 and above generic notes
- [ ] Video URL → CEO brief + playbook visible in vault within one session
- [ ] Follow-up draft from Agency queue opens email w/ evidence-linked structure (not wall of text)
- [ ] Delegate creates handoff w/ real doc id + pickup line (Ras anti-pattern compliant)
- [ ] Intel items show PROVEN vs CLAIMED when from CEO brief pipeline

---

## Agent prompt — implement transcript tier (Wave 1)

> **Pre-flight check:** before running this prompt, confirm PRD Phases 3 and 4 have shipped (or are at least merged into the active branch). Wave 1 builds on PRD-3's job actions (G-01) and PRD-4's morning ritual + wire filters (G-17, G-14). If those aren't in, run the PRD prompts first — see `docs/vault-prd-cross-reference.md` §6 for ready-to-paste versions.

```
Read docs/vault-ceo-transcript-insights.md, docs/vault-cmd-center-prd.md,
and docs/vault-prd-cross-reference.md.

Implement Wave 1 (T-A1, T-A2, T-A3, T-A5):
1. Extend build_cmd_center() with quick_read{} and human_item{} (single scored pick).
2. Add stale_days + fit_score to job priority_queue rows from job pipeline store.
   (Prereq: services/jobs/brief.py must already expose both fields — see
   cross-ref §4 conflict #2. If not, add that first as Chunk 0.)
3. Render CEO Quick Read strip in cmdCenter.js under topbar.
4. Style the one HUMAN row distinctly in priority queue; add NEEDLE/SPIN badges from scoring rules in insights doc.
5. Tests in test_home_dashboard.py for human_item selection and stale sorting.

Do not start video ingest (T-B1) until Wave 1 passes pytest and manual 45s scan test.
```

---

## Out of scope (from transcripts)

- Token-maxxing / subscription arbitrage (Fable) — not product features
- Full git PR judge workflows — needs git host integration
- Hermes desktop app / Ollama install wizard — Cookbook already covers models
- CPG-specific CRM — use Notion notes tags until CRM branch exists

---

## File index for future agents

| Need | Read |
|------|------|
| CEO brief format | `data/skills/general/youtube-ceo-brief/SKILL.md` |
| Morning ops logic | `prompts/ras-morning-brief.md` |
| CEO email tone | `chat2workflow_email_followups.md` (§ MorningAI Follow-Up Process) |
| Multi-agent ops | `Fable5_yt_trancript.md` |
| Private/local OS | `hermes_agent_yt_transcript.md` |
| Vault engineering gaps | `docs/vault-cmd-center-prd.md` |
| This synthesis | `docs/vault-ceo-transcript-insights.md` |

---

*Drafted 2026-07-04 from CEO transcript docs + V.A.U.L.T. session context.*
