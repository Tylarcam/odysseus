# Olivia — Local-Model Executive Brief Solution

**Audience:** Olivia (foundation executive workflow)  
**Prepared for review by:** Tylar  
**Status:** Draft — ready for demo planning

---

## What Olivia Needs

From her inquiry about Claude best practices:

1. **Privacy-first summarization** — meeting notes → executive brief + action items without sending sensitive board/foundation content to cloud APIs.
2. **Local model option** — runs on her own hardware (VRAM/CPU dependent).
3. **Delegatable agent workflow** — an agent that follows documented standards, do/don'ts, and context when routing work.
4. **Board-ready polish** — a workflow credible enough to present to her foundation's executive board.

---

## Recommended Architecture

```
Meeting notes (paste or import)
        ↓
   Odysseus (self-hosted)
   ├── Local model (Ollama) — brief + action-item extraction
   ├── Skills / Memory — delegation rules, do/don'ts, org context
   ├── Documents — store briefs, standards, meeting archives
   └── Tasks — schedule recurring briefs, reminders on action items
        ↓
Executive brief (markdown) + structured action items
        ↓
Optional: delegate non-sensitive items to cloud agent (Cursor/Claude)
```

**Why Odysseus:** It is already built for local-first AI workspaces — chat, agent tools, documents, notes, scheduled tasks, and Cookbook (VRAM-aware model recommendations). Olivia gets one self-hosted app instead of stitching together five tools.

---

## Local Model Options by Hardware

| Profile | Typical hardware | Recommended stack | Brief quality |
|---------|------------------|-------------------|---------------|
| **Light** | 8 GB RAM, no GPU or integrated graphics | Ollama + Qwen3 4B / Phi-4 mini / Llama 3.2 3B | Good for bullet summaries; verify action-item accuracy |
| **Standard** | 16 GB unified (M-series Mac) or 12–16 GB VRAM | Ollama + Qwen3 14B / Mistral Nemo 12B / Llama 3.1 8B | Strong briefs; reliable action-item extraction |
| **Executive** | 24 GB+ VRAM or 32 GB+ RAM (Apple Silicon) | Ollama + Qwen3 32B (Q4) / Nemotron / Llama 3.3 70B (Q4) | Board-ready prose; handles nuance and delegation reasoning |

### Platform notes

- **Windows:** Ollama is the easiest path. Point Odysseus at `http://localhost:11434/v1` in Settings → Models.
- **macOS (Apple Silicon):** Run Odysseus natively (`./start-macos.sh`) for GPU-accelerated Cookbook; Ollama uses Metal automatically.
- **NVIDIA GPU (12 GB+ VRAM):** Ollama with Nemotron / Llama 3.x, or **NVIDIA NIM** containers for optimized inference. Odysseus Cookbook can recommend fit-scored models for her card.
- **OpenRouter (non-sensitive only):** Add as a secondary endpoint in Settings → Models for drafts, research, or formatting when content is not board-confidential. Never use for marked-sensitive documents.
- **Hybrid (recommended):** Local model for sensitive briefs; route redacted External-delegate items to OpenRouter or Claude via Odysseus handoffs.

Odysseus Cookbook scans hardware and recommends fit-scored models — Olivia can click to download and serve without guessing VRAM math.

---

## Privacy Posture

| Control | Setting |
|---------|---------|
| Data residency | All meeting notes, briefs, and action items stay on Olivia's machine |
| Model inference | Local Ollama — no API calls for sensitive work |
| Network exposure | Bind to `127.0.0.1`; use Tailscale or VPN if remote access needed |
| Authentication | `AUTH_ENABLED=true` (default); separate accounts if staff share the instance |
| Cloud fallback | Explicit opt-in per task — never automatic for marked-sensitive documents |
| Audit | Documents + session history in local SQLite; no third-party logging |

**Talking point for the board:** "Sensitive foundation deliberations never leave our infrastructure. The AI runs on hardware we control."

---

## Delegation Workflow

Olivia's standards and do/don'ts live in Odysseus **Skills** and **Memory**, referenced by the executive-brief agent on every run.

| Step | What happens |
|------|--------------|
| 1. Ingest | Paste meeting notes into a Document or drop a transcript file |
| 2. Brief | Agent runs `prompts/executive-brief-template.md` against local model |
| 3. Extract | Output: executive summary, decisions, action items (owner, deadline, priority) |
| 4. Classify | Each action item tagged: **Olivia**, **Staff delegate**, **External**, or **Defer** |
| 5. Route | Sensitive → stay local; research/drafts → handoff to Claude/Cursor with redacted packet |
| 6. Track | Action items become checklist items in Notes; due dates trigger reminders |

Reusable template: [`prompts/executive-brief-template.md`](../../prompts/executive-brief-template.md)

---

## What to Install (Minimal Path)

1. **Ollama** — https://ollama.com/download  
2. **Odysseus** — Docker (`docker compose up`) or native per README  
3. **One local model** — start with Cookbook recommendation or `ollama pull qwen3:14b`  
4. **Executive brief skill** — copy template into Odysseus Skills or a scheduled Task prompt  
5. **Standards doc** — one Document with org do/don'ts; link from skill context  

Estimated setup time: **30–60 minutes** on a machine that already meets the hardware profile.

---

## Cost Comparison (for board conversation)

| Approach | Monthly cost | Privacy |
|----------|-------------|---------|
| Claude/ChatGPT Team | $25–30/user + usage | Data processed by vendor |
| Local Odysseus + Ollama | $0 ongoing (hardware already owned) | Full local control |
| Hybrid (local briefs + cloud research) | Usage-based for non-sensitive only | Sensitive stays local |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Small model misses action items | Use Standard/Executive tier; human review step in template |
| Windows GPU serving limited | Ollama handles Windows GPU; avoid vLLM on bare Windows |
| Staff need remote access | Tailscale + HTTPS; never public internet exposure |
| Model quality varies | Cookbook fit scoring; side-by-side Compare tool for model selection |

---

## Next Step for Tylar

Review [`demo-plan.md`](demo-plan.md), run the 15-minute demo script once locally, then schedule Olivia's walkthrough.
