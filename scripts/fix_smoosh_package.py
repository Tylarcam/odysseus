"""One-shot fix for Smoosh AI CTO package docs + approval note."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "app.db"

COVER_ID = "3d6f6566-2aa3-47f6-9721-dd3c42251510"
RESUME_ID = "7d880f79-5aa5-4e12-864e-9424b778e89a"
APPROVAL_NOTE_ID = "e170d040-5fcb-4e79-8bdc-0a5c9386b37b"

COVER = """# Cover Letter — Smoosh AI, Chief Technology Officer

**Tylar Campbell**
tylarcam@alumni.stanford.edu | 858-322-1558 | San Diego, CA (open to SF Bay Area)

---

Janice,

Thanks for reaching out on Handshake about the CTO role at Smoosh AI — I appreciate you flagging the fit.

I'm a technical founder and builder who ships production software end-to-end: FastAPI backends, TypeScript frontends, OAuth/API integrations, and AI tooling people use daily. I'm a Ph.D. candidate at Simon Fraser University (Interactive Arts & Technology), AI instructor at Columbia Justice Through Code, and architect of **(Agentic Harness)** — a local-first agentic productivity platform with calendar, email, notes, and multi-model orchestration.

What I'd bring as CTO at an early-stage company:

**I've built and operated full product stacks.** From model-serving infrastructure (vLLM, Ollama, remote GPUs) to the application layer — I own architecture, deployment, and iteration cadence. I deploy on Railway, manage remote infrastructure, and ship daily.

**I'm integration-native.** Calendar sync, email pipelines, OAuth flows, background jobs, structured APIs — the plumbing early products depend on. My current platform connects real productivity workflows to agent tooling; that maps directly to products that coordinate people, time, and data.

**I'm CTO-shaped, not memo-shaped.** As co-founder of No Brainer Co., I set product direction and drove GTM experiments. At Ethos Lab I led cross-functional delivery and secured $1M+ from Unity and Meta. I translate between engineers, users, and stakeholders — including teaching non-traditional learners at Columbia.

I'd love to hear what Smoosh AI is building, where the technical roadmap is headed, and how a hands-on CTO could accelerate the next phase.

Best,
Tylar"""

RESUME = """# Tylar Campbell — Resume (Smoosh AI · CTO)

**tylarcam@alumni.stanford.edu | 858-322-1558 | San Diego, CA (open to SF Bay Area)**
**github.com/tylarcam | linkedin.com/in/tylar-campbell | tylarcampbell.com**

---

## TARGET

**Chief Technology Officer @ Smoosh AI** — Direct recruiter outreach via Janice Nam (Handshake). Reply with cover letter + attached resume.

---

## PROFESSIONAL SUMMARY

Technical founder and full-stack builder with production experience across Python/TypeScript, API integrations, and AI product systems. Ph.D. candidate (SFU), Vanier Scholar, Columbia AI instructor. Architect of **(Agentic Harness)** — a shipped local-first agent platform with calendar/email/notes integration, multi-model orchestration, and background automation. Co-founder experience, $1M+ product funding outcomes, and a track record moving from architecture to deployed product in weeks — not quarters.

---

## TECHNICAL LEADERSHIP

**(Agentic Harness) — Ambient Agent Platform** (2025–Present)
- Architected local-first agent OS: multi-model routing (Claude, GPT, local LLMs), tool-use pipelines, persistent memory, scheduled jobs
- Built productivity integrations: calendar (CalDAV), email (IMAP), notes/todos, document library, agent relay across Cursor/Claude/Codex
- Model serving: vLLM, SGLang, Ollama, llama.cpp on remote GPU infrastructure
- Stack: Python, FastAPI, TypeScript, SQLite, Docker, Railway, HuggingFace

**No Brainer Co. — Co-Founder** (2023–2025)
- AI product direction: lead qualification agents, RAG pipelines, CRM automation (n8n, LangChain, Claude API)
- Revenue-first GTM: Upwork, LinkedIn, Railway deployments

**Ethos Lab — Director of Product Development** (2022–2023)
- Led Atlanthos Box (AI/XR curriculum toolkit) from requirements through pilots in 3 schools; 98% on-time delivery
- Secured $1M+ funding from Unity and Meta

---

## AI / ENGINEERING

- **Integrations:** OAuth, REST APIs, CalDAV, IMAP, webhooks, background schedulers, structured agent tool calls
- **ML / AI:** LLM orchestration, evaluation frameworks, prompt engineering, HuggingFace, multimodal validation
- **Infra:** Docker, tmux, SSH remote ops, Railway, SQLite, Git/GitHub
- **Languages:** Python (primary), TypeScript, SQL, Bash

---

## TEACHING & LEADERSHIP

**Columbia University — AI Instructor, Justice Through Code** (2025–Present)
- Teach AI/ML deployment to 20+ fellows; curriculum: Python, ML fundamentals, practical AI systems

**Handshake AI — Model Validation Specialist** (2025–2026)
- Built QA rubrics and validation workflows for multimodal enterprise AI systems

---

## EDUCATION

- **Simon Fraser University** — Ph.D., Interactive Arts & Technology (2021–Present) · GPA 3.9
- **Stanford University** — M.A., Communication / Data Journalism (2019–2020)
- **UCLA** — B.A., African American Studies (2016–2019)

## SELECTED HONORS

Vanier-Banting Canadian Graduate Scholar (SSHRC) · ProPublica Diversity Award · McClatchy Journalism Fellowship (Stanford) · Hugging Face AI Agents Fundamentals

---

## WHY SMOOSH AI

1. **Ships production software** — (Agentic Harness) is a working multi-agent system, not a slide deck.
2. **Integration depth** — calendar, email, scheduling-adjacent workflows are core to what I build.
3. **Early-stage CTO range** — architecture + hands-on coding + product direction + stakeholder translation.
4. **Bay Area ready** — relocating for the right founding technical role."""

APPROVAL = """[Swarm · APPROVE] send: Smoosh AI CTO application → Janice Nam via Handshake

**Idempotency Key:** `smoosh-cto-2026-07-12-tylar`

**Revised 2026-07-12** — Cursor review pass: removed unverified gen-AI / smoosh.dev claims; fixed education (SFU, Stanford M.A., UCLA); fixed contact (github.com/tylarcam, phone, San Diego).

**Drafts:**
- [Cover Letter](#document-3d6f6566-2aa3-47f6-9721-dd3c42251510) — reply to Janice, honest CTO framing
- [Resume](#document-7d880f79-5aa5-4e12-864e-9424b778e89a) — attach as PDF (export from doc before send)

**Channel:** Handshake (alumni.stanford.edu) — UID 19f3f173ddb843a8
**Recipient:** Janice Nam
**What to send:** Paste cover letter into Handshake message + attach resume PDF

**Checklist:**
[ ] 0: Export resume doc to PDF
[ ] 1: Paste cover letter into Handshake message to Janice Nam
[ ] 2: Attach resume PDF
[ ] 3: Send — then log to Fruit Ledger"""


def _update_document(cur: sqlite3.Cursor, doc_id: str, content: str) -> None:
    cur.execute("SELECT version_count FROM documents WHERE id = ?", (doc_id,))
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"document not found: {doc_id}")
    new_ver = int(row[0]) + 1
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """
        INSERT INTO document_versions (id, document_id, version_number, content, summary, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), doc_id, new_ver, content, "Cursor fix — Smoosh package review", "user", now),
    )
    cur.execute(
        "UPDATE documents SET current_content = ?, version_count = ?, updated_at = ? WHERE id = ?",
        (content, new_ver, now, doc_id),
    )


def _update_note(cur: sqlite3.Cursor, note_id: str, content: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "UPDATE notes SET content = ?, updated_at = ? WHERE id = ?",
        (content, now, note_id),
    )


def main() -> None:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    try:
        for doc_id, content in [(COVER_ID, COVER), (RESUME_ID, RESUME)]:
            _update_document(cur, doc_id, content)
            print(f"updated doc {doc_id[:8]}…")
        _update_note(cur, APPROVAL_NOTE_ID, APPROVAL)
        print(f"updated note {APPROVAL_NOTE_ID[:8]}…")
        con.commit()
    finally:
        con.close()


if __name__ == "__main__":
    main()
