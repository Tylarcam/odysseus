# Demo Plan — Olivia Local-Model Executive Brief

**Duration:** 15–20 minutes live (plus 30 min prep)  
**Goal:** Show Olivia that sensitive meeting notes → executive brief + action items can run entirely on her hardware.

---

## Prep (Tylar, before the call)

| Step | Action | Time |
|------|--------|------|
| 1 | Confirm Olivia's machine: OS, RAM, GPU/VRAM (Apple Silicon vs Windows vs Linux) | 5 min |
| 2 | Install Ollama + pull one model matching her tier (see solution-brief hardware table) | 10 min |
| 3 | Install Odysseus (Docker or native) — verify login at `http://localhost:7000` | 10 min |
| 4 | Settings → Models → add Ollama endpoint `http://localhost:11434/v1` | 2 min |
| 5 | Create Document: `Foundation Standards — Do/Don'ts` (sample content below) | 5 min |
| 6 | Create Task or paste `prompts/executive-brief-template.md` as skill/prompt | 5 min |
| 7 | Run demo once yourself with sample notes (below) — confirm brief quality | 5 min |

### Sample standards doc (paste into Odysseus Documents)

```markdown
# Foundation Communication Standards

## Do
- Use "the Foundation" in external-facing summaries
- Flag any action touching endowment policy for executive review
- Include grant program names when referencing disbursements

## Don't
- Include individual donor names in briefs shared outside executive team
- Commit to public statements without comms approval
- Send meeting content to cloud AI services marked Confidential
```

### Sample meeting notes (demo input)

Use the example from `prompts/executive-brief-template.md` (Finance Committee notes).

---

## Demo Script (live with Olivia)

### 1. Frame the problem (2 min)

> "You wanted meeting notes turned into executive briefs without sending sensitive board content to Claude or ChatGPT. This runs on your machine — the model, the notes, and the brief never leave your computer."

Show: Odysseus Settings → Models → local Ollama endpoint (not OpenAI/Anthropic).

### 2. Show privacy posture (2 min)

- Odysseus bound to localhost
- No API key required for brief generation
- Optional: "For research that isn't confidential, you can still hand off to Claude — but sensitive briefs stay local."

Reference: [`solution-brief.md`](solution-brief.md) privacy table.

### 3. Live brief generation (5 min)

1. Open Documents → paste sample Finance Committee notes (or Olivia's redacted real notes if she provides them).
2. Open Chat or run the Executive Brief Task with local model selected.
3. Paste prompt: "Generate executive brief from the open document."
4. Walk through output sections:
   - Executive Summary
   - Key Decisions
   - Action Items table (owner, due, priority)
   - Delegation Notes

**Success signal:** Olivia sees action items she recognizes, with correct owners/deadlines.

### 4. Show delegation rules (3 min)

1. Open Foundation Standards document.
2. Explain: "The agent reads these do/don'ts every time. If something violates a rule, it flags it."
3. Point to `Do / Don't Reminders` section in the brief output.

### 5. Show action-item tracking (2 min)

- Convert one action item to a Note checklist item (manual or ask agent).
- Show reminder/notification option in Notes.

### 6. Hardware path for her machine (3 min)

| If she has… | Recommend |
|-------------|-----------|
| M2/M3 MacBook, 16 GB+ | Native Odysseus + Ollama; Qwen3 14B or similar |
| Windows laptop, 16 GB VRAM GPU | Ollama + Qwen3 14B |
| Windows, no GPU | Ollama CPU mode + smaller model; set expectations on speed |
| Wants zero local setup | Not recommended for sensitive work — offer hybrid with air-gapped brief step |

Offer: "I can send a one-page setup guide keyed to your exact specs."

### 7. Board angle (2 min)

> "This is self-hosted infrastructure — no per-seat AI subscription, no vendor data retention. The foundation controls the hardware, the model, and the archive."

Hand her: [`solution-brief.md`](solution-brief.md) cost comparison section.

---

## Artifacts to send after demo

1. [`solution-brief.md`](solution-brief.md) — full architecture + hardware guide
2. [`prompts/executive-brief-template.md`](../../prompts/executive-brief-template.md) — reusable prompt
3. Odysseus README Quick Start link for her platform
4. Optional: 5-minute Loom of the demo if she wants to share with board IT

---

## Success criteria

- [ ] Brief generated entirely on local model
- [ ] Action items table has ≥3 items with owners and priorities
- [ ] Do/don't rules reflected in output
- [ ] Olivia confirms she would trust this for internal (not yet board-external) use
- [ ] Clear next step agreed: self-setup vs Tylar-assisted install

---

## Fallbacks

| Issue | Fallback |
|-------|----------|
| Local model too slow | Pre-generate brief before call; show live on smaller input |
| Model quality weak on her hardware | Show Compare tool with two models; recommend hardware upgrade path |
| Olivia wants cloud for non-sensitive only | Demo handoff packet with redaction example |
| Install blocked by IT | Docker on approved VM; or Mac mini as dedicated brief appliance |

---

## Relay note (internal — not for Olivia)

The Odysseus → Cursor handoff relay failed previously because `agent.ps1` was launched directly instead of via `powershell.exe`. Fixed in `scripts/handoff-relay-watcher.ps1` (`New-AgentProcessStartInfo` wraps `.ps1`/`.cmd`/`.bat`). Verified on Windows 2026-06-18.
