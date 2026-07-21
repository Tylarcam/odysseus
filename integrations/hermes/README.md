# Hermes ↔ Odysseus

Hermes connects as an external agent over the same scoped bus as Claude/Codex: **`/api/codex/*`** + Bearer token.

## Skills

| Skill | Purpose |
|-------|---------|
| [`skills/odysseus-vps-write/`](skills/odysseus-vps-write/) | Long-form note/document writes that avoid Hermes Tirith / approval hangs |

### Hermes VPS install path

On this VPS, Hermes home is `HOME=/opt/data`. Skills live **directly under** `/opt/data/`, not under `~/.hermes/skills/`.

```bash
# From the odysseus repo on a machine that can reach the VPS:
cp -r integrations/hermes/skills/odysseus-vps-write /opt/data/odysseus-vps-write
```

Canonical runtime paths:

- Skill root: `/opt/data/odysseus-vps-write/`
- Helper: `/opt/data/odysseus-vps-write/scripts/ody_write.py`
- Config: `/opt/data/config.yaml`

Requires `ODYSSEUS_URL` and `ODYSSEUS_API_TOKEN` (Settings → Integrations → Claude/Codex Agent).

See also: `docs/handoffs/2026-07-18-hermes-odysseus-architecture.md`.
