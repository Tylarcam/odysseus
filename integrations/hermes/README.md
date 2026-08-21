# Hermes ↔ Odysseus

Hermes connects as an external agent over the same scoped bus as Claude/Codex: **`/api/codex/*`** + Bearer token.

## Skills

| Skill | Purpose |
|-------|---------|
| [`skills/odysseus-vps-write/`](skills/odysseus-vps-write/) | Long-form note/document writes that avoid Hermes Tirith / approval hangs |
| [`skills/aether-transcribe/`](skills/aether-transcribe/) | Hermes VPS → laptop Aether YouTube transcription (verified JSON gate) |

### Hermes VPS install path

On this VPS, Hermes home is `HOME=/opt/data`. Skills live **directly under** `/opt/data/`, not under `~/.hermes/skills/`.

```bash
# From the odysseus repo on a machine that can reach the VPS:
cp -r integrations/hermes/skills/odysseus-vps-write /opt/data/odysseus-vps-write
cp -r integrations/hermes/skills/aether-transcribe /opt/data/aether-transcribe
```

Canonical runtime paths:

- Skill root: `/opt/data/odysseus-vps-write/`
- Helper: `/opt/data/odysseus-vps-write/scripts/ody_write.py`
- Aether remote runner: `/opt/data/aether-transcribe/scripts/aether_remote.py`
- Aether job staging: `/opt/data/aether-jobs/`
- Config: `/opt/data/config.yaml`

Requires `ODYSSEUS_URL` and `ODYSSEUS_API_TOKEN` (Settings → Integrations → Claude/Codex Agent).

For YouTube briefs: use `aether_remote.py` only — never VPS-side yt-dlp as the primary path. SSH key auth from VPS → laptop (`AETHER_SSH_HOST`, default Tailscale `100.93.33.88`) is required. See `skills/aether-transcribe/SKILL.md`.

See also: `docs/handoffs/2026-07-18-hermes-odysseus-architecture.md`.
