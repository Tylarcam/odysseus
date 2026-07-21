# Odysseus Claude Code Integration

This directory contains the Claude Code skill bundle for Odysseus.

## User Flow

1. Open Odysseus Settings > Integrations.
2. Add a Claude Agent.
3. Copy the full setup commands shown after the generated token.
4. Toggle the tools Claude is allowed to use.
5. Configure credentials for Claude Code, Cursor, and handoff scripts.

Add to your Odysseus `.env` (see `.env.example` → External agent clients):

```bash
ODYSSEUS_URL=http://127.0.0.1:7000
ODYSSEUS_API_TOKEN=ody_generated_token
```

**Recommended — persistent env (set once, all new terminals inherit):**

Windows PowerShell:

```powershell
[System.Environment]::SetEnvironmentVariable('ODYSSEUS_URL', 'http://127.0.0.1:7000', 'User')
[System.Environment]::SetEnvironmentVariable('ODYSSEUS_API_TOKEN', 'ody_generated_token', 'User')
```

macOS/Linux (`~/.bashrc` or `~/.zshrc`):

```bash
export ODYSSEUS_URL=http://127.0.0.1:7000
export ODYSSEUS_API_TOKEN=ody_generated_token
```

`'User'` on Windows stores vars in your profile (not just the current shell). Restart Claude Code / Cursor after setting.

**One-session only** (bash):

```bash
export ODYSSEUS_URL=http://your-odysseus-host:7000
export ODYSSEUS_API_TOKEN=ody_generated_token
```

6. Install the skill bundle:

```bash
mkdir -p ~/.claude
curl -fsSL -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" "$ODYSSEUS_URL/api/claude/plugin.zip" -o /tmp/odysseus-claude-skill.zip
python3 -m zipfile -e /tmp/odysseus-claude-skill.zip ~/.claude/
```

Claude Code auto-loads anything under `~/.claude/skills/`. The bundled `odysseus_api.py` and `handoff_api.py` scripts also auto-load `ODYSSEUS_*` from `~/code/odysseus/.env` when env vars are unset.

## What's in the bundle

- `skills/odysseus/SKILL.md` — the skill definition Claude Code reads.
- `skills/odysseus/scripts/odysseus_api.py` — small helper that calls the scoped
  `/api/codex/*` endpoints (these are the canonical scope-gated agent API; the
  `codex` path is historic and shared by all agent integrations).

## Scope enforcement

The token is scope-gated. Every tool surface is checked server-side in Odysseus,
so even if Claude tries to call a forbidden endpoint, it gets `403` until the
user enables the matching toggle in Settings > Integrations > Claude Agent.
