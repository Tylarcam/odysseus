# Hermes Agent Setup â€” Step by Step

**Question:** Hermes Agent setup step by step: install, config, MCP/Blender, troubleshooting, cost, alternatives  
**Engines:** A1 last30days Â· A2 Firecrawl Â· A3 Perplexity (`perplexity_research` fallback; Odysseus `perplexity_agent` 403)  
**Date:** 2026-07-16  
**Session:** `rp-hermes-agent-setup-20260716`  
**Category:** howto  

---

## Coach briefing / Executive summary

Hermes Agent is Nous Researchâ€™s open-source autonomous agent (not an IDE copilot). Official install lives at [hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs/) and [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent). On Windows: Desktop installer or `iex (irm https://hermes-agent.nousresearch.com/install.ps1)`; elsewhere `curl â€¦/install.sh | bash`. Get one chat working via `hermes setup --portal` or `hermes model` before MCP. Blender: `hermes mcp install blender` + ahujasid addon + Connect bridge each session â€” promo videos naming the one-liner are directionally right but incomplete. Cost: software free/OSS; you pay model/Portal tokens. Skip Hermes if you only need Cursor/Copilot inline help. **Next:** install â†’ doctor â†’ portal/model â†’ chat â†’ optional Blender MCP.

---

## Numbered step-by-step setup

### 1. What is Hermes Agent / official source?

**Hermes Agent** = self-improving AI agent by **Nous Research** (skills, memory, multi-platform gateway, MCP).  
**Authoritative sources only:**

| Source | URL |
|--------|-----|
| Docs | https://hermes-agent.nousresearch.com/docs/ |
| Installation | https://hermes-agent.nousresearch.com/docs/getting-started/installation |
| Quickstart | https://hermes-agent.nousresearch.com/docs/getting-started/quickstart |
| Repo | https://github.com/NousResearch/hermes-agent |

Promo (Julian Goldie / AI Profit Lab, [youtu.be/D4hk_D4VMCY](https://youtu.be/D4hk_D4VMCY)): awareness only â€” verify every command against docs.

### 2. Prerequisites

- **Git** (required). Linux: also `curl`, `xz-utils`. Desktop on Debian/Ubuntu: `build-essential`.
- Installer auto-installs: **uv**, **Python 3.11**, **Node.js v22**, **ripgrep**, **ffmpeg**.
- **Model:** â‰¥ **64K** context window ([Quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart)).
- Blender path later: Blender 3.0+ desktop, display (or Xvfb).

### 3. Install (exact documented commands)

**A. Desktop (macOS / Windows recommended)**  
Download from https://hermes-agent.nousresearch.com/ and run the installer.

**B. CLI â€” Linux / macOS / WSL2 / Termux**

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc   # or: source ~/.zshrc
hermes
```

**C. CLI â€” Windows native (PowerShell)**

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

Optional: `hermes desktop` after CLI-only install. Optional skip browser: install with `--skip-browser`.

### 4. First-run / config / models / MCP baseline

1. Fast path: `hermes setup --portal` (OAuth â†’ Nous + Tool Gateway).  
2. Or: `hermes model` / `hermes setup` (Full Setup / Blank Slate).  
3. Chat: `hermes` or `hermes --tui`. Confirm replies before adding features.  
4. Secrets â†’ `~/.hermes/.env`; settings â†’ `~/.hermes/config.yaml`.  
5. MCP ships with install. Catalog: `hermes mcp` / `hermes mcp install <name>`. Manual servers under `mcp_servers` in config.yaml ([MCP docs](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md)).

### 5. Install / enable Blender MCP (documented)

From official skill ([blender-mcp/SKILL.md](https://github.com/NousResearch/hermes-agent/blob/main/optional-skills/creative/blender-mcp/SKILL.md)):

1. `hermes mcp install blender`  
2. Download https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py â†’ Blender â†’ Preferences â†’ Add-ons â†’ Install â†’ enable **Interface: Blender MCP**.  
3. **Each session:** open Blender â†’ `N` â†’ BlenderMCP â†’ **Connect to Claude** â†’ then start Hermes.  
4. Headless: `xvfb-run blender` (addon refuses `blender -b`).  
5. Optional services: `hermes mcp configure blender`.

**Do not confuse** with Blender Lab MCP ([blender.org/lab/mcp-server](https://www.blender.org/lab/mcp-server/), Blender 5.1+) â€” different stack.

### 6. Common failures / troubleshooting

| Issue | Action |
|-------|--------|
| `hermes: command not found` | Reload shell; put `~/.local/bin` on PATH |
| `API key not set` | `hermes model` / `hermes config set â€¦` |
| Stale config post-update | `hermes config check` â†’ `hermes config migrate` |
| `ModuleNotFoundError: dotenv` | Use `~/.local/bin/hermes` venv launcher |
| Empty replies | Re-auth provider via `hermes model` |
| MCP tools missing | Check connect/filters/`enabled`; `/reload-mcp` |
| Blender connection refused | Blender up + Connect clicked |
| Bridge timeouts | Smaller `execute_blender_code` steps |

Recovery toolkit (docs order): `hermes doctor` â†’ `hermes model` â†’ `hermes setup` â†’ `hermes sessions list` â†’ `hermes --continue` â†’ `hermes gateway status`.

### 7. Cost model (free vs paid)

| Layer | Free / OSS? | Notes |
|-------|-------------|-------|
| Hermes Agent software | Yes | GitHub / docs installers |
| Blender | Yes | blender.org |
| Hermes MCP + blender catalog entry | Yes (OSS) | Catalog install command free |
| LLM / Tool Gateway | Paid (usually) | Nous Portal credits, OpenRouter, Anthropic, etc. |
| Infra | Optional cost | VPS / GPU / serverless if you host always-on |

â€œFree foreverâ€ YouTube claims refer to software, not tokens.

### 8. Alternatives / when not to use Hermes

**Prefer something else when:** you only need IDE autocomplete (Cursor/Copilot); you want a managed chat UI with no agent runtime; you refuse multi-step local setup; or you want Blender Labâ€™s first-party MCP with another LLM client (not Hermes).

**Prefer Hermes when:** you want a persistent, model-agnostic agent with skills/memory, messaging gateway, and curated MCP (including Blender) â€” including Odysseus/Cursor-adjacent automation.

---

## Landscape / people / org

- **Org:** Nous Research (Hermes / Nomos / Psyche lineage).  
- **Community promo:** Julian Goldie SEO / AI Profit Lab â€” upsell communities; not the install authority.  
- **Related:** Blender Foundation Lab MCP (parallel, different product).

## Risks, gaps, open questions

- Odysseus `perplexity_agent` blocked (403 scope-aware route) â€” A3 used Docker Perplexity.  
- Exact Portal dollar tiers should be checked live on portal.nousresearch.com.  
- TinyFish deferred (not needed; Firecrawl covered authority pages).  
- Child Task subagents stalled; digests written by orchestrator from live scrapes.

---


## Appendix — research legs

### A1 Recency

## A1 Recency Digest

*Engine: Firecrawl search (last ~30 days) + official docs cross-check. Window relative to 2026-07-16.*

### Key signals (bullets with dates if known)

- **Official Hermes Agent (Nous Research) is the product of record** â€” docs at [hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs/) and repo [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent). Positioning: self-improving autonomous agent with learning loop, not an IDE copilot.
- **Native Windows + Desktop installer path is actively documented** â€” Installation/Quickstart pages recommend Hermes Desktop on macOS/Windows; CLI one-liners remain for Linux/macOS/WSL2/Termux and native Windows PowerShell (`install.sh` / `install.ps1`).
- **Blender MCP catalog install is real and officially documented** â€” optional skill `blender-mcp` (v2.1.0) documents `hermes mcp install blender`, then Blender addon install from [ahujasid/blender-mcp](https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py), then connect bridge each session. NousResearch social copy also surfaces the same one-liner.
- **Promo wave around Hermes + Blender MCP** â€” Julian Goldie SEO video [youtu.be/D4hk_D4VMCY](https://youtu.be/D4hk_D4VMCY) markets â€œimagination printerâ€ / one-command setup and AI Profit Lab upsell. Install command matches official skill; addon + Blender-first connect steps are often under-explained in promo.
- **Separate Blender Foundation Lab MCP** â€” [blender.org/lab/mcp-server](https://www.blender.org/lab/mcp-server/) documents Blenderâ€™s own Lab MCP (Blender 5.1+, different addon/stack). Do not conflate with Hermesâ€™s catalog `blender` entry (community blender-mcp bridge).
- **Community install chatter** â€” Termux single-script install posts, local/LM Studio demos, and â€œrun free foreverâ€ YouTube titles. Treat as anecdotal; prefer official install + `hermes doctor`.
- **Fast-path messaging from Nous** â€” docs push `hermes setup --portal` (OAuth + Tool Gateway) as the fastest first-run path after install.

### Quotes / posts worth knowing

- Official docs: *â€œThe self-improving AI agent built by Nous Researchâ€¦ not a coding copilot tethered to an IDE.â€* â€” [docs home](https://hermes-agent.nousresearch.com/docs/)
- Blender MCP skill: *â€œInstall the MCP server from the Nous catalog (one-time): `hermes mcp install blender`â€* then addon + *â€œstart Blender FIRSTâ€¦ Connect to Claudeâ€* â€” [SKILL.md](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/optional-skills/creative/blender-mcp/SKILL.md)
- NousResearch (X search snippet): *â€œEasily activate and install the Blender MCP by running `hermes mcp install blender`â€¦â€* â€” [x.com/NousResearch](https://x.com/NousResearch)
- Promo (verify only): Goldie claims Blender/MCP/install are free; tokens are the paid layer â€” aligns directionally with OSS Hermes + paid model APIs, but â€œfree API inside Hermesâ€ claims need provider-specific verification.

### Implications for the research question

1. **Setup guide should lead with official Nous install docs**, not YouTube. Exact commands are public and stable on the docs site.
2. **Blender MCP is a multi-step stack**: catalog MCP install â‰  full readiness. Addon + live Blender bridge each session are required per official skill.
3. **Distinguish two Blender MCP worlds**: Hermes catalog (`ahujasid/blender-mcp` bridge) vs Blender Lab MCP (5.1+). Builders wiring Cursor/Claude/Odysseus-adjacent stacks should pick one intentionally.
4. **Cost story is layered**: Hermes + Blender + MCP OSS/free; model/provider (and optional Nous Portal subscription / Tool Gateway) is where money appears.
5. Recency content is heavy on **hype demos**; use them for awareness, not as install authority.

### Sources (url list)

- https://hermes-agent.nousresearch.com/docs/
- https://hermes-agent.nousresearch.com/docs/getting-started/installation
- https://hermes-agent.nousresearch.com/docs/getting-started/quickstart
- https://github.com/NousResearch/hermes-agent
- https://raw.githubusercontent.com/NousResearch/hermes-agent/main/optional-skills/creative/blender-mcp/SKILL.md
- https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/features/mcp.md
- https://www.blender.org/lab/mcp-server/
- https://youtu.be/D4hk_D4VMCY
- https://x.com/NousResearch
- https://www.reddit.com/r/termux/comments/1ubyijw/i_installed_hermes_agent_using_a_single_script_on/


### A2 Authority

## A2 Authority Digest

*Engine: Firecrawl scrape (markdown). Scraped 2026-07-16. Firecrawl available for all listed URLs unless noted.*

### Hermes Agent (product / official source)

- **What:** Self-improving autonomous AI agent by [Nous Research](https://nousresearch.com/) â€” learning loop (skills, memory, cross-session recall), multi-platform gateway, MCP client/server, model-agnostic. Explicitly *not* an IDE coding copilot.
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

**Model requirement (Quickstart):** â‰¥ **64,000** tokens context; smaller local models rejected at startup.

**Blender MCP extras:** Blender 3.0+ desktop (skill); addon from ahujasid/blender-mcp; display or `xvfb-run blender` for headless.

### Install steps (exact commands)

**Recommended (macOS/Windows Desktop):** download installer from https://hermes-agent.nousresearch.com/ and run it.

**CLI â€” Linux / macOS / WSL2 / Termux:**

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc   # or ~/.zshrc
hermes
```

**CLI â€” Windows native (PowerShell):**

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
hermes setup --portal   # OAuth â†’ Nous provider + Tool Gateway
hermes                  # or: hermes --tui
hermes doctor           # if anything feels wrong
```

Other setup modes: Full Setup (BYO keys), Blank Slate (minimal tools; MCP off until opted in).

Config split:

- Secrets â†’ `~/.hermes/.env`
- Non-secrets â†’ `~/.hermes/config.yaml`

Useful commands: `hermes model`, `hermes tools`, `hermes setup`, `hermes config set|get`, `hermes gateway setup`.

**MCP** ([mcp.md](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/features/mcp.md)):

- Ships with standard install.
- Catalog: `hermes mcp` / `hermes mcp catalog` / `hermes mcp install <name>`
- Manual YAML under `mcp_servers:` (stdio `command`/`args`/`env` or HTTP `url`/`headers`).
- Reload: `/reload-mcp` or restart; MCP deps: `cd ~/.hermes/hermes-agent && uv pip install -e ".[mcp]"` if needed.

### Blender MCP setup

From official skill [blender-mcp/SKILL.md](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/optional-skills/creative/blender-mcp/SKILL.md):

1. `hermes mcp install blender` â€” pins catalog stdio server; tools: `get_scene_info`, `get_object_info`, `get_viewport_screenshot`, `execute_blender_code`.
2. Install addon: download https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py â†’ Blender â†’ Edit â†’ Preferences â†’ Add-ons â†’ Install â†’ enable **Interface: Blender MCP**.
3. **Every session:** start Blender â†’ `N` â†’ BlenderMCP tab â†’ **Connect to Claude** â†’ then start Hermes.
4. Headless: addon refuses `blender -b`; use `xvfb-run blender`.
5. Optional asset tools: `hermes mcp configure blender`.

**Note:** Blender Foundation Lab MCP ([blender.org/lab/mcp-server](https://www.blender.org/lab/mcp-server/)) is a **different** stack (Blender 5.1+, Lab addon). Not the Hermes catalog path.

### Troubleshooting / common failures

| Symptom | Fix (from docs) |
|---------|-----------------|
| `hermes: command not found` | `source` shell; ensure `~/.local/bin` on PATH |
| `API key not set` | `hermes model` or `hermes config set â€¦` |
| Missing config after update | `hermes config check` â†’ `hermes config migrate` |
| Empty/broken replies | Re-run `hermes model`; verify provider auth |
| `ModuleNotFoundError: dotenv` | Use venv launcher (`~/.local/bin/hermes`), not raw repo script |
| MCP tools missing | Server connected? filters? `enabled: false`? restart / `/reload-mcp` |
| Blender â€œconnection refusedâ€ | Blender running + addon Connect clicked; donâ€™t retry blindly |
| Bridge timeouts | Smaller `execute_blender_code` chunks |
| General | Recovery order: `hermes doctor` â†’ `model` â†’ `setup` â†’ `sessions list` â†’ `--continue` â†’ `gateway status` |

### Cost signals (from docs only)

- Hermes Agent: open-source (GitHub).
- Installer / MCP / Blender: no Hermes license fee documented.
- **Paid layer:** model providers (Nous Portal subscription + credits, OpenRouter, Anthropic, OpenAI, etc.) and optional Tool Gateway usage via Portal.
- Quick Setup: *â€œfree OAuth login, no API keysâ€* for Portal path â€” does not mean unlimited free inference; Portal has paid subscription tiers (external portal pages).
- Docs do not claim Hermes Desktop is paid; Desktop download is from official site.

### Alternatives / when not to use (authority framing)

Docs contrast Hermes with IDE copilots and single-API chatbots. Prefer alternatives when you only need:

- Inline IDE completion (Cursor/Copilot alone)
- Stateless one-off chat
- Fully managed SaaS with zero local/agent runtime

Hermes fits persistent agent + tools + messaging + MCP, not â€œjust chat.â€

### Source excerpts (short quotes + URLs)

> â€œGet Hermes Agent up and running in under two minutes!â€ â€” https://hermes-agent.nousresearch.com/docs/getting-started/installation

> `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash` â€” same

> â€œMCP support ships with the standard install â€” no extra step needed.â€ â€” mcp.md (repo)

> â€œhermes mcp install blenderâ€ / â€œStart Blender FIRSTâ€¦ Connect to Claudeâ€ â€” blender-mcp SKILL.md

> â€œHermes Agent requires a model with at least 64,000 tokens of context.â€ â€” Quickstart

**URLs successfully scraped:** docs home, installation, quickstart, mcp.md (raw), blender-mcp SKILL.md (raw), blender.org Lab MCP, GitHub repo page (Firecrawl).


### A3 Perplexity

## A3 Perplexity Digest

*Engine: Docker MCP `perplexity_research` (fallback). Odysseus `POST /api/research/start` with `perplexity_agent` returned HTTP 403 (â€œAPI tokens must use a scope-aware API routeâ€). Raw narrative saved as `a3_perplexity_raw.json` (text research output).*

### Findings (numbered, cited)

1. **Official product:** Hermes Agent by Nous Research â€” open-source self-improving agent. Canonical sources: [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) and [hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs/). ([Perplexity synthesis + Firecrawl-verified docs])

2. **Prerequisites:** Git (plus Linux curl/xz-utils); installer brings Python 3.11 (via uv), Node 22, ripgrep, ffmpeg. Model must support â‰¥64K context. ([Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation), [Quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart))

3. **Install commands (documented):**
   - Desktop: download from hermes-agent.nousresearch.com
   - Unix/WSL/Termux: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`
   - Windows PowerShell: `iex (irm https://hermes-agent.nousresearch.com/install.ps1)`
   - Then reload shell â†’ `hermes`

4. **First-run:** Prefer `hermes setup --portal` (OAuth + Tool Gateway), else `hermes model` / Full Setup / Blank Slate. Secrets in `~/.hermes/.env`, settings in `config.yaml`. Verify with a plain chat before adding gateway/MCP/skills. ([Quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart))

5. **MCP enablement:** Included in standard install. Catalog: `hermes mcp` / `hermes mcp install <name>`. Or YAML `mcp_servers` for stdio/HTTP. Hermes can also `hermes mcp serve` for Cursor/Claude Code clients. ([MCP docs](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md))

6. **Blender MCP (official skill):** `hermes mcp install blender` â†’ install ahujasid `addon.py` in Blender â†’ enable Interface: Blender MCP â†’ each session Connect bridge *before* Hermes. Tools: scene/object info, viewport screenshot, execute_blender_code. ([SKILL.md](https://github.com/NousResearch/hermes-agent/blob/main/optional-skills/creative/blender-mcp/SKILL.md))

7. **Promo reconciliation:** Julian Goldie video ([youtu.be/D4hk_D4VMCY](https://youtu.be/D4hk_D4VMCY)) correctly names `hermes mcp install blender` and free OSS layers, but underplays addon + Connect-each-session; â€œminutes per sceneâ€ / free API brand names are marketing, not docs guarantees.

8. **Troubleshooting:** PATH/`hermes: command not found`; API key/provider misconfig; dotenv when wrong launcher; MCP filter/connect failures; Blender connection refused if bridge not up; use `hermes doctor` recovery sequence. ([Installation troubleshooting](https://hermes-agent.nousresearch.com/docs/getting-started/installation), Quickstart common failures)

9. **Cost model:** Hermes + Blender + MCP software free/OSS. Paid: LLM tokens (Nous Portal tiers/credits, OpenRouter, Anthropic, etc.), optional infra (VPS/GPU). Tool Gateway bundled under Portal path. ([docs + Portal references in research])

10. **When not to use Hermes:** Need only IDE inline completion; want zero local/agent ops; intolerant of multi-step config; or prefer Blender Labâ€™s native MCP stack with a different LLM client rather than Hermes catalog blender-mcp.

### Contradictions / uncertainty

- **Two Blender MCP products:** Hermes catalog (`ahujasid/blender-mcp`, Blender 3.0+) vs Blender Lab MCP (Blender 5.1+). Promo rarely distinguishes.
- **â€œFree foreverâ€ YouTube titles** conflict with real token/Portal costs â€” software free â‰  inference free.
- **Odysseus perplexity_agent** unavailable in this run (403 scope); synthesis used Docker Perplexity + authority scrapes.
- Exact current Nous Portal dollar tiers not fully scraped here â€” check [portal.nousresearch.com](https://portal.nousresearch.com/) live.

### Implications

Builder path for Odysseus/Cursor-adjacent stacks: install Hermes CLI on Windows via `install.ps1` or Desktop â†’ get chat working with Portal or BYO key â†’ add MCP catalog entries â†’ for Blender, follow skillâ€™s three-step (mcp install + addon + Connect). Do not trust promo one-liners as complete setup. Wire other agents to Hermes messaging via `hermes mcp serve` if needed.

### Sources

- https://hermes-agent.nousresearch.com/docs/
- https://hermes-agent.nousresearch.com/docs/getting-started/installation
- https://hermes-agent.nousresearch.com/docs/getting-started/quickstart
- https://github.com/NousResearch/hermes-agent
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md
- https://github.com/NousResearch/hermes-agent/blob/main/optional-skills/creative/blender-mcp/SKILL.md
- https://www.blender.org/lab/mcp-server/
- https://youtu.be/D4hk_D4VMCY
- https://portal.nousresearch.com/
