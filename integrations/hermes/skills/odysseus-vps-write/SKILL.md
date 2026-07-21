---
name: odysseus-vps-write
description: >-
  Write long-form content to Odysseus from Hermes/VPS without tripping Hermes
  Tirith / dangerous-command approval. Use when POSTing notes or documents via
  odysseus_api, with-ody-env, or any shell that embeds markdown JSON in argv —
  especially payloads with words like delete, destroy, BLOCKED, destructive.
---

# Odysseus VPS Write (Hermes-safe)

**Goal:** Persist notes/documents to Odysseus through `/api/codex/*` without hanging on an invisible Hermes approval prompt.

## Root cause (do not re-litigate)

| Layer | Role |
|-------|------|
| **Hermes** `approvals.*` + **Tirith** | Scans the **shell command string** before exec. Large JSON in argv with operational vocab → approval prompt → gateway timeout → kill. |
| **Odysseus** `/api/codex/*` | No keyword/size confirm on note/document create. Token scopes only. |

Config on official Docker Hermes: `/opt/data/config.yaml` (same as `~/.hermes/config.yaml`):

```yaml
approvals:
  mode: smart          # smart | manual | off
  timeout: 60          # unanswered → deny
security:
  tirith_enabled: true
  tirith_fail_open: true
command_allowlist: []  # filled by "always" approvals
```

Docs: https://hermes-agent.nousresearch.com/docs/user-guide/security

`GET /api/codex/capabilities` → `destructive_actions_should_confirm: true` is **advisory for clients**, not an Odysseus server gate.

## Hard rules

1. **Never put long markdown / JSON bodies in the shell argv.** Write a file, then call a helper that reads the file.
2. **Smoke-test first** with a ~20-byte benign title/content if the token/path is unproven this session.
3. **Do not** treat `/opt/data/notes/` (Hermes local `HERMES_WRITE_SAFE_ROOT`) as Odysseus Notes. Staging only; still POST afterward.
4. **Do not** disable Tirith / set `approvals.mode: off` / YOLO as the default fix. Prefer tempfile + helper.
5. Only `/api/codex/*` with Bearer token. No SQLite, no SSH into Odysseus data dirs for user writes.

## Surfaces

| Intent | Endpoint | Scope | Payload shape |
|--------|----------|-------|---------------|
| Markdown **note** | `POST /api/codex/todos` | `todos:write` | see below |
| Library **document** | `POST /api/codex/documents` | `documents:write` | `title`, `content`, `language` |
| Short reminder/todo | `POST /api/codex/todos` | `todos:write` | `action`, `title`, optional `due_date` |
| Durable fact | `POST /api/codex/memory` | `memory:write` | `text`, `category` |

### Note fields (correct names)

```json
{
  "action": "add",
  "title": "...",
  "content": "...",
  "note_type": "note",
  "label": "agent"
}
```

| Wrong | Right |
|-------|-------|
| `body` as only field | `content` (aliases `body`/`text` exist, prefer `content`) |
| `tags` | `label` (single string) |
| assume checklist-only | set `note_type: "note"` |

### Document fields

```json
{
  "title": "...",
  "content": "...",
  "language": "markdown"
}
```

## Canonical workflow

### Preferred: helper script (body never in argv)

```bash
# 1) Write markdown body to a file (path only appears on the next command line)
cat > /tmp/ody-body.md <<'EOF'
## Your long markdown
Words like delete / destroy / BLOCKED are fine *inside the file*.
EOF

# 2) Note (VPS path)
python3 /opt/data/odysseus-vps-write/scripts/ody_write.py note \
  --title "Hermes: short title" \
  --content-file /tmp/ody-body.md \
  --label agent

# 3) Or document
python3 /opt/data/odysseus-vps-write/scripts/ody_write.py document \
  --title "Hermes: short title" \
  --content-file /tmp/ody-body.md
```

### Install / paths

| Where | Path |
|-------|------|
| **Hermes VPS (canonical)** | `/opt/data/odysseus-vps-write/` — Hermes home is `HOME=/opt/data`. **`~/.hermes/skills/` is not used on this VPS.** |
| Repo (source of truth) | `integrations/hermes/skills/odysseus-vps-write/` |
| Helper on VPS | `/opt/data/odysseus-vps-write/scripts/ody_write.py` |

Sync from repo → VPS:

```bash
cp -r integrations/hermes/skills/odysseus-vps-write /opt/data/odysseus-vps-write
```

### Do not expand JSON into the shell

`odysseus_api.py POST … '{huge json}'` and `$(cat payload.json)` both put the body into argv → same Tirith trip. Prefer `ody_write.py`.

### Smoke test (optional, new session)

```bash
python3 /opt/data/odysseus-vps-write/scripts/ody_write.py smoke
```

Expect JSON with `note_id` / `exit_code: 0` in under 1s. No approval prompt.

## If an approval prompt still appears

1. Look at Hermes **TUI / Telegram / Discord / gateway chat** — not Odysseus UI.
2. Reply `yes` / `approve`, or choose **always** to add a `command_allowlist` entry.
3. Unanswered → `approvals.timeout` (default 60s) → **deny**.
4. Last resort for a trusted automation session only: `HERMES_YOLO_MODE=1` or `approvals.mode: off` (hardline blocklist still applies).

## Anti-patterns (re-discovered friction)

- Embedding 2KB+ markdown with `delete`/`destroy`/`BLOCKED`/`destructive` in `python … POST '{…}'`
- Saving to `/opt/data/notes/` and calling it “saved to Odysseus”
- Using `tags` / wrong note field names and concluding the API “doesn’t take body”
- Disabling Tirith because Odysseus “blocked” a write (it didn’t)

## Success report

Tell the user:

- surface (`note` or `document`)
- `title`
- `note_id` or document id (short prefix OK)
- `open_url` when present (e.g. `/#open=notes&note=<uuid>`)
