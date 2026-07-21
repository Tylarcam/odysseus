---
name: handoff
description: >-
  Transfer work context between Odysseus, Cursor, and Claude Code. Use when the
  user says handoff to cursor, handoff to claude, handoff to odysseus, handoff to hermes, pick up
  handoff, or wants to continue work in another agent. Requires ODYSSEUS_URL
  and ODYSSEUS_API_TOKEN (same as the odysseus skill).
---

# Handoff

Move structured work context between **Odysseus**, **Cursor**, **Claude Code**, and **Hermes** via Odysseus documents — not raw chat exports.

Requires the **odysseus** skill credentials (`ODYSSEUS_URL`, `ODYSSEUS_API_TOKEN`). If missing, load from the project's `.env` before running commands (PowerShell does not auto-source `.env`):

```powershell
Get-Content "C:\Users\tylar\code\odysseus\.env" | Where-Object { $_ -match '^ODYSSEUS_' } | ForEach-Object {
  $parts = $_ -split '=', 2; [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1]) }
```

Helper script paths (use whichever exists in this session):

- Claude Code: `~/.claude/skills/handoff/scripts/handoff_api.py`
- Cursor: `~/.cursor/skills/handoff/scripts/handoff_api.py`

Re-install from Odysseus: Settings → Integrations → Claude Agent → download plugin zip (includes this skill).

## When to use

| User says | Action |
|-----------|--------|
| "handoff to cursor" | `create cursor` from current tool |
| "handoff to claude" | `create claude` from current tool |
| "handoff to odysseus" | `create odysseus` from current tool |
| "pick up handoff" | `pickup <this-tool>` — cursor in Cursor, claude in Claude Code |
| "what handoffs are waiting?" | `list --pending` |

## Outbound: create a handoff

Before creating, summarize the session into **Goal**, **Context**, **Done so far**, and **Next steps**. Do not dump the full chat.

```bash
python ~/.cursor/skills/handoff/scripts/handoff_api.py create cursor \
  --from odysseus \
  --title "Hero page for Traversing Spaces" \
  --goal "Complete the Hero/Landing page and send to supervisor." \
  --project "C:\\Users\\tylar\\code\\traversing-spaces" \
  --todo 0629dce7 \
  --context "Supervisor wants minimal aesthetic, mobile-first" \
  --done "Wireframe approved in last session" \
  --next "Build hero section component" \
  --next "Deploy preview and email supervisor"
```

`--from` is the tool you are in now: `odysseus`, `cursor`, or `claude`.

Tell the user the `next_action` from the JSON output — e.g. *"In Cursor, say: Pick up handoff abc123"*.

**Job handoffs:** When the body includes `## Full job description`, `create` auto-runs `materialize-jd` and writes `positions/_active/<folder>/JD.md` under job-application-ops. The create JSON includes `materialized_jd.jd_path` when sync succeeds.

## Inbound: pick up a handoff

**Mandatory sequence** — when the user says "pick up handoff" or names a handoff by title/ID:

1. Run pickup (scripts auto-load `ODYSSEUS_*` from `C:\Users\tylar\code\odysseus\.env` if env vars are unset):
2. If the handoff body contains `## Full job description`, **use that text as the JD**. Do **not** web-search Handshake or re-scrape the URL.
3. For resume/application work, materialize the JD to the local job-app workspace, then follow that project's `CLAUDE.md`:

```bash
python ~/.claude/skills/handoff/scripts/handoff_api.py pickup claude --id DOC_ID
python ~/.claude/skills/handoff/scripts/handoff_api.py materialize-jd --id DOC_ID
cd ~/code/notion/Projects/job-application-ops
```

```bash
# Latest pending handoff for this tool
python ~/.claude/skills/handoff/scripts/handoff_api.py pickup claude

# Specific handoff by document id
python ~/.claude/skills/handoff/scripts/handoff_api.py pickup claude --id DOC_ID
```

After pickup:

1. Run the **Agent bootstrap** block from the handoff body (env vars + `cd` to project).
2. Execute **Next steps** in order.
3. Do not re-read the entire Odysseus chat history — the packet is the source of truth.
4. **JD source priority:** handoff `## Full job description` → materialized `positions/_active/*/JD.md` → never web search if either exists.

## List and inspect

```bash
python ~/.cursor/skills/handoff/scripts/handoff_api.py list --pending
python ~/.cursor/skills/handoff/scripts/handoff_api.py list --to cursor --pending
python ~/.cursor/skills/handoff/scripts/handoff_api.py get DOC_ID
```

## Handoff document format

Stored in Odysseus documents with title prefix `handoff → {target}:` and YAML frontmatter:

```yaml
---
handoff_version: 1
source: odysseus
target: cursor
status: pending
project: C:\Users\tylar\code\traversing-spaces
created_at: 2026-06-12T...
todo_ids: 0629dce7
---
```

Body sections: **Goal**, **Context**, **Done so far**, **Next steps**, **Open questions**, **Agent bootstrap**.

## Rules

- All handoff data goes through `/api/codex/documents` — never bypass with SQLite, SSH, or direct file writes to Odysseus data dirs.
- One handoff = one focused task. Split unrelated work into separate handoffs.
- Always include `--project` when the work is repo-bound.
- Link `--todo ID` when a todo already tracks the work.
- Keep **Next steps** actionable (imperative verbs, specific files/commands where known).
- V1 does not auto-mark handoffs as picked-up; the receiving agent owns execution from the packet.

## Handshake job applications (job-application-ops)

**Do not hand off mid-flow** for PDF conversion or Handshake upload — one agent completes tailor → PDF → upload in one session. See `job-application-ops/config/handshake-apply-workflow.md`.

When creating a handoff for a Handshake role, **required**:

- `--project C:\Users\tylar\code\notion\Projects\job-application-ops`
- `--goal` with Handshake job ID and company/role
- `--next` steps through materialize JD, tailor, PDF, upload (or state what's already done)
- Body must include `## Full job description` **or** path to `positions/_active/<folder>/JD.md`
- `--done` listing files already written (DOCX/PDF paths if exist)

**Banned:** title-only handoffs like "Handshake Job Posting Review" with no JD, no folder, no next steps.

Browser for Handshake: **browser-harness + Comet** (`BU_CDP_URL=http://127.0.0.1:9333`). Not Docker MCP Playwright.

## Safety

Same scope rules as the **odysseus** skill. If document write returns `403`, ask the user to enable Documents write in Settings → Integrations → Claude Agent.
