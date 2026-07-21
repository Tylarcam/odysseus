# Handoff → Hermes: Odysseus continuity architecture

**Created:** 2026-07-18  
**Source:** Cursor (architecture session with Tylar)  
**Target agent:** Hermes Agent (Nous Research)  
**Project:** `C:\Users\tylar\code\odysseus`  
**Status:** pending — architecture + connection prep (not full implementation)

---

```yaml
---
handoff_version: 1
source: cursor
target: hermes
status: pending
project: C:\Users\tylar\code\odysseus
created_at: 2026-07-18T21:29:00Z
---
```

## Goal

Design and prep the **highest-leverage connection** between Hermes Agent and Odysseus so Hermes has continuity of workspace state (what's active, todos, memory, handoffs) and can participate in **delegation / orchestration** — without inventing a parallel data plane.

Deliverable of this handoff: a short architecture decision + a working connection checklist Hermes can execute (credentials, skill install, session-start ritual). Optional Phase 2: scaffold `integrations/hermes/` in the Odysseus repo.

## Context

- **Odysseus** is Tylar's main Life OS workspace (todos, memory, calendar, documents, email, job pipeline, Agent Bin / handoffs).
- **Hermes** (Nous Research, https://hermes-agent.nousresearch.com/) is a long-running autonomous agent (skills, local memory, MCP client, gateway/cron) — not an IDE copilot.
- **Claude Code** and **Codex** already connect via the same pattern:
  1. Scoped token from Odysseus **Settings → Integrations**
  2. Skill bundle (`odysseus` + `handoff`)
  3. HTTP calls to **`/api/codex/*`** (path name is historic; shared by all external agents)
- There is **no first-party Hermes integration** yet. Do not assume one exists.
- Handoff targets today are only: `cursor | claude | odysseus` (`VALID_TARGETS` in `src/handoff_packet.py`). Hermes can still *create* packets to those targets; native `target: hermes` is Phase 2+.
- Odysseus is primarily an **MCP client** (consumes MCP servers). It is **not** currently an MCP server for the scoped agent API. Prefer REST + skills over inventing MCP wrapping first.

### Verified in-repo anchors (do not re-litigate)

| Claim | Location |
|-------|----------|
| Agent bus = `/api/codex/*` | `integrations/claude/README.md`, `integrations/codex/README.md`, skills |
| Claude install zip | `GET $ODYSSEUS_URL/api/claude/plugin.zip` with Bearer token |
| Codex install zip | `GET $ODYSSEUS_URL/api/codex/plugin.zip` |
| Helper scripts | `integrations/claude/skills/odysseus/scripts/odysseus_api.py`, `.../handoff/scripts/handoff_api.py` |
| Valid handoff targets | `src/handoff_packet.py` → `VALID_TARGETS = {cursor, claude, odysseus}` |
| Prior Hermes research | `research-orch/hermes-agent-setup-20260716/master_report.md` |
| Agentic OS / blackboard direction | `docs/agentic-life-os-build-spec.md` (handoff + blackboard; Hermes not named as first-class yet) |

### Recommended architecture (non-negotiable for this prep)

```
┌─────────────┐     Bearer token      ┌──────────────────┐
│   Hermes    │ ───────────────────►  │  /api/codex/*    │
│  (executor  │   skills + scripts    │  scoped agent API│
│  /orchestr) │ ◄───────────────────  │                  │
└─────────────┘   todos/memory/docs   └────────┬─────────┘
                                               │
                    ┌──────────────────────────▼──────────┐
                    │         Odysseus (source of truth)   │
                    │  todos · memory · docs/handoffs · cal│
                    └──────────────────────────┬──────────┘
                                               │
                    ┌──────────────┬───────────┴───────────┐
                    ▼              ▼                       ▼
               Cursor         Claude Code            Odysseus UI
            (code handoffs)  (code handoffs)      (human + Agent Bin)
```

**Roles**

| System | Owns |
|--------|------|
| Odysseus | Workspace truth, scopes, handoff documents, human visibility |
| Hermes | Long-running loops, cron/gateway, orchestration that *reads/writes Odysseus* |
| Cursor/Claude | Focused coding execution via handoff packets |

**Anti-goals**

- Do **not** SSH into Odysseus, query SQLite, or call MCP internals for user data.
- Do **not** treat Hermes `~/.hermes/memories/` as the workspace of record (may mirror summaries; write durable facts to Odysseus memory/notes).
- Do **not** build a full MCP server wrapping Odysseus as Phase 0 — REST + skills match Claude/Codex and ship faster.
- Do **not** expand `VALID_TARGETS` until Phase 0 connection works and Tylar approves Phase 2.

## Done so far

- Cursor session mapped Hermes ↔ Odysseus options and recommended the Claude/Codex mirror path.
- Confirmed Hermes MCP config lives in `~/.hermes/config.yaml` / secrets in `~/.hermes/.env` (official docs).
- Confirmed no `integrations/hermes/` directory exists yet.
- This handoff document written at `docs/handoffs/2026-07-18-hermes-odysseus-architecture.md`.

## Next steps (execute in order)

### Phase 0 — Connect Hermes to the existing agent bus (no Odysseus code required)

1. **Human (Tylar):** Odysseus → Settings → Integrations → Add **Claude Agent** (or Codex Agent). Enable at minimum:
   - todos read/write  
   - memory read/write  
   - documents read/write  
   - calendar read (optional write)  
   - email only if needed later  
2. Put credentials in Hermes secrets:

```bash
# ~/.hermes/.env
ODYSSEUS_URL=http://127.0.0.1:7000   # or LAN/Tailscale URL
ODYSSEUS_API_TOKEN=ody_...
```

3. Install skill bundle into Hermes skills dir (adapt path if Hermes uses a different skills root — confirm with `hermes` docs / `~/.hermes/skills/`):

```powershell
$odyUrl = $env:ODYSSEUS_URL
$token = $env:ODYSSEUS_API_TOKEN
curl.exe -fsSL -H "Authorization: Bearer $token" "$odyUrl/api/claude/plugin.zip" -o "$env:TEMP\odysseus-claude-skill.zip"
# Extract skills/odysseus and skills/handoff into ~/.hermes/skills/
```

4. Smoke test:

```bash
python ~/.hermes/skills/odysseus/scripts/odysseus_api.py capabilities
python ~/.hermes/skills/odysseus/scripts/odysseus_api.py todos list
python ~/.hermes/skills/handoff/scripts/handoff_api.py list --pending
```

5. Add a **session-start ritual** to Hermes identity (`SOUL.md` or a small skill `odysseus-continuity`):

```
On every new work session before planning:
1. GET /api/codex/capabilities (or odysseus_api.py capabilities)
2. List open todos
3. List pending handoffs
4. Pull recent memory relevant to active projects
5. Summarize "what's active" in one short block, then proceed
When finishing material work: write durable facts to Odysseus memory;
create handoff packets for coding work (target: cursor or claude).
```

6. Write a 1-page **Architecture Decision Record** (ADR) as an Odysseus document or note titled `ADR: Hermes ↔ Odysseus connection`, confirming:
   - REST `/api/codex/*` as the bus  
   - Odysseus as source of truth  
   - Handoff docs for delegation  
   - Local Hermes memory = cache only  

### Phase 1 — Prove continuity (still minimal code)

1. From Hermes: create a todo in Odysseus ("Hermes continuity probe").
2. From Hermes: POST a memory fact ("Hermes connected via scoped API on YYYY-MM-DD").
3. From Hermes: create a handoff **to cursor** with a trivial next step (proves delegation path).
4. Confirm items appear in Odysseus UI (todos + Agent Bin / documents).

### Phase 2 — Only after Tylar approves (repo changes, ≤5 files per phase)

Propose (do not implement until approved):

1. `integrations/hermes/README.md` — install steps for Hermes Desktop/CLI on Windows.  
2. `integrations/hermes/skills/odysseus/` — copy/adapt Claude skill with Hermes paths (`~/.hermes/...`).  
3. Optional later: add `hermes` to `VALID_TARGETS` in `src/handoff_packet.py` (+ JS/builder copies) so Agent Bin can address Hermes natively.  
4. Optional later: thin MCP wrapper over `/api/codex/*` *if* Hermes prefers MCP tools over shell scripts — second-class to Phase 0.

## Open questions (Hermes should answer in the ADR)

1. Exact Hermes skills directory + how custom skills are registered on this install (Desktop vs CLI).
2. Preferred Odysseus URL for Hermes (localhost vs Tailscale vs always-on host) given gateway/cron.
3. Should Hermes run always-on gateway and poll pending handoffs, or only pull on session start?
4. Scope set: start read-heavy (todos/memory/docs) vs full write + email?

## Agent bootstrap

```powershell
# Load Odysseus agent credentials if unset
Get-Content "C:\Users\tylar\code\odysseus\.env" | Where-Object { $_ -match '^ODYSSEUS_' } | ForEach-Object {
  $parts = $_ -split '=', 2
  [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1])
}
cd "C:\Users\tylar\code\odysseus"

# Read this packet
# docs/handoffs/2026-07-18-hermes-odysseus-architecture.md

# Official Hermes references
# https://hermes-agent.nousresearch.com/docs/
# https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
# https://hermes-agent.nousresearch.com/docs/user-guide/configuration
```

In Hermes: treat this file as the source of truth. Execute **Phase 0**, then answer **Open questions** in an ADR. Stop for human approval before any Odysseus repo edits (Phase 2).

## Acceptance criteria (Phase 0–1)

- [ ] Hermes can call `capabilities` with a scoped token (no 401/403 for enabled scopes).
- [ ] Hermes can list todos and pending handoffs.
- [ ] Session-start ritual documented in Hermes (`SOUL.md` or skill).
- [ ] ADR written confirming REST bus + Odysseus as source of truth.
- [ ] Probe todo + memory + outbound handoff visible in Odysseus UI.
- [ ] No SQLite/SSH/MCP-bypass paths used for user data.
- [ ] No Odysseus code changes until Phase 2 is explicitly approved.

---

## Paste-ready prompt for Hermes

Copy everything below the line into Hermes:

---

You are Hermes Agent. Pick up this architecture handoff for connecting yourself to Odysseus (Tylar's Life OS).

**Goal:** Prep the architecture and connection that makes the most sense for workspace continuity, active-work awareness, and delegation/orchestration. Prefer the proven Claude/Codex pattern over inventing a new protocol.

**Hard constraints**
- All Odysseus user data access via scoped HTTP `/api/codex/*` with `ODYSSEUS_URL` + `ODYSSEUS_API_TOKEN`.
- Never SSH, Docker-exec, SQLite, or MCP internals for Odysseus user data.
- Odysseus is source of truth; your local `~/.hermes/memories/` is cache/working notes only.
- Do not modify the Odysseus repo until Tylar approves Phase 2.
- Handoff targets today: `cursor`, `claude`, `odysseus` only — create packets to those; do not add `hermes` to VALID_TARGETS yet.

**Read first**
- `C:\Users\tylar\code\odysseus\docs\handoffs\2026-07-18-hermes-odysseus-architecture.md` (full packet)
- `C:\Users\tylar\code\odysseus\integrations\claude\README.md`
- `C:\Users\tylar\code\odysseus\integrations\claude\skills\odysseus\SKILL.md`
- `C:\Users\tylar\code\odysseus\integrations\claude\skills\handoff\SKILL.md`

**Execute Phase 0–1** from that file: credentials in `~/.hermes/.env`, install odysseus+handoff skills into Hermes skills dir, smoke-test capabilities/todos/handoffs, add session-start ritual, write ADR, run probe writes.

**Return to Tylar**
1. Connection status (what worked / what blocked).
2. ADR summary (5–10 bullets).
3. Recommendation: stay on REST+skills only, or schedule Phase 2 `integrations/hermes/` + optional `target: hermes`.
4. Answers to Open questions.

Stop after Phase 1 unless asked to implement Phase 2.
