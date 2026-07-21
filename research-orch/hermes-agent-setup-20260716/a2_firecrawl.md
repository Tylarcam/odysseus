## A2 Authority Digest

*Engine: Firecrawl scrape (markdown). Scraped 2026-07-16. Firecrawl available for all listed URLs unless noted.*

### Hermes Agent (product / official source)

- **What:** Self-improving autonomous AI agent by [Nous Research](https://nousresearch.com/) — learning loop (skills, memory, cross-session recall), multi-platform gateway, MCP client/server, model-agnostic. Explicitly *not* an IDE coding copilot.
- **Official sources:**
  - Docs: https://hermes-agent.nousresearch.com/docs/
  - Repo: https://github.com/NousResearch/hermes-agent
  - Site/Desktop download: https://hermes-agent.nousresearch.com/

### Prerequisites

From [Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation):

| Platform | You need beforehand | Installer provides |
|----------|---------------------|--------------------|
| Non-Windows | **Git** (+ Linux: `curl`, `xz-utils`) | uv, Python 3.11, Node.js v22, ripgrep, ffmpeg |
| Desktop app (Linux) | also `g++` / `build-essential` | native modules compile |
| Windows | Desktop installer **or** PowerShell script; WSL2 also supported | same stack via installer |

You do **not** need to pre-install Python/Node/ripgrep/ffmpeg manually.

**Model requirement (Quickstart):** ≥ **64,000** tokens context; smaller local models rejected at startup.

**Blender MCP extras:** Blender 3.0+ desktop (skill); addon from ahujasid/blender-mcp; display or `xvfb-run blender` for headless.

### Install steps (exact commands)

**Recommended (macOS/Windows Desktop):** download installer from https://hermes-agent.nousresearch.com/ and run it.

**CLI — Linux / macOS / WSL2 / Termux:**

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc   # or ~/.zshrc
hermes
```

**CLI — Windows native (PowerShell):**

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

**After CLI-only install, Desktop:**

```bash
hermes desktop
```

**Skip browser deps (optional):**

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-browser
```

**Layout (per-user):** code `~/.hermes/hermes-agent/`, binary `~/.local/bin/hermes`, data `~/.hermes/`.

### First-run / configuration / MCP

Fastest path ([Quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart)):

```bash
hermes setup --portal   # OAuth → Nous provider + Tool Gateway
hermes                  # or: hermes --tui
hermes doctor           # if anything feels wrong
```

Other setup modes: Full Setup (BYO keys), Blank Slate (minimal tools; MCP off until opted in).

Config split:

- Secrets → `~/.hermes/.env`
- Non-secrets → `~/.hermes/config.yaml`

Useful commands: `hermes model`, `hermes tools`, `hermes setup`, `hermes config set|get`, `hermes gateway setup`.

**MCP** ([mcp.md](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/features/mcp.md)):

- Ships with standard install.
- Catalog: `hermes mcp` / `hermes mcp catalog` / `hermes mcp install <name>`
- Manual YAML under `mcp_servers:` (stdio `command`/`args`/`env` or HTTP `url`/`headers`).
- Reload: `/reload-mcp` or restart; MCP deps: `cd ~/.hermes/hermes-agent && uv pip install -e ".[mcp]"` if needed.

### Blender MCP setup

From official skill [blender-mcp/SKILL.md](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/optional-skills/creative/blender-mcp/SKILL.md):

1. `hermes mcp install blender` — pins catalog stdio server; tools: `get_scene_info`, `get_object_info`, `get_viewport_screenshot`, `execute_blender_code`.
2. Install addon: download https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py → Blender → Edit → Preferences → Add-ons → Install → enable **Interface: Blender MCP**.
3. **Every session:** start Blender → `N` → BlenderMCP tab → **Connect to Claude** → then start Hermes.
4. Headless: addon refuses `blender -b`; use `xvfb-run blender`.
5. Optional asset tools: `hermes mcp configure blender`.

**Note:** Blender Foundation Lab MCP ([blender.org/lab/mcp-server](https://www.blender.org/lab/mcp-server/)) is a **different** stack (Blender 5.1+, Lab addon). Not the Hermes catalog path.

### Troubleshooting / common failures

| Symptom | Fix (from docs) |
|---------|-----------------|
| `hermes: command not found` | `source` shell; ensure `~/.local/bin` on PATH |
| `API key not set` | `hermes model` or `hermes config set …` |
| Missing config after update | `hermes config check` → `hermes config migrate` |
| Empty/broken replies | Re-run `hermes model`; verify provider auth |
| `ModuleNotFoundError: dotenv` | Use venv launcher (`~/.local/bin/hermes`), not raw repo script |
| MCP tools missing | Server connected? filters? `enabled: false`? restart / `/reload-mcp` |
| Blender “connection refused” | Blender running + addon Connect clicked; don’t retry blindly |
| Bridge timeouts | Smaller `execute_blender_code` chunks |
| General | Recovery order: `hermes doctor` → `model` → `setup` → `sessions list` → `--continue` → `gateway status` |

### Cost signals (from docs only)

- Hermes Agent: open-source (GitHub).
- Installer / MCP / Blender: no Hermes license fee documented.
- **Paid layer:** model providers (Nous Portal subscription + credits, OpenRouter, Anthropic, OpenAI, etc.) and optional Tool Gateway usage via Portal.
- Quick Setup: *“free OAuth login, no API keys”* for Portal path — does not mean unlimited free inference; Portal has paid subscription tiers (external portal pages).
- Docs do not claim Hermes Desktop is paid; Desktop download is from official site.

### Alternatives / when not to use (authority framing)

Docs contrast Hermes with IDE copilots and single-API chatbots. Prefer alternatives when you only need:

- Inline IDE completion (Cursor/Copilot alone)
- Stateless one-off chat
- Fully managed SaaS with zero local/agent runtime

Hermes fits persistent agent + tools + messaging + MCP, not “just chat.”

### Source excerpts (short quotes + URLs)

> “Get Hermes Agent up and running in under two minutes!” — https://hermes-agent.nousresearch.com/docs/getting-started/installation

> `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash` — same

> “MCP support ships with the standard install — no extra step needed.” — mcp.md (repo)

> “hermes mcp install blender” / “Start Blender FIRST… Connect to Claude” — blender-mcp SKILL.md

> “Hermes Agent requires a model with at least 64,000 tokens of context.” — Quickstart

**URLs successfully scraped:** docs home, installation, quickstart, mcp.md (raw), blender-mcp SKILL.md (raw), blender.org Lab MCP, GitHub repo page (Firecrawl).
