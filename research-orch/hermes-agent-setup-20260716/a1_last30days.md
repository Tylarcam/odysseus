## A1 Recency Digest

*Engine: Firecrawl search (last ~30 days) + official docs cross-check. Window relative to 2026-07-16.*

### Key signals (bullets with dates if known)

- **Official Hermes Agent (Nous Research) is the product of record** — docs at [hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs/) and repo [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent). Positioning: self-improving autonomous agent with learning loop, not an IDE copilot.
- **Native Windows + Desktop installer path is actively documented** — Installation/Quickstart pages recommend Hermes Desktop on macOS/Windows; CLI one-liners remain for Linux/macOS/WSL2/Termux and native Windows PowerShell (`install.sh` / `install.ps1`).
- **Blender MCP catalog install is real and officially documented** — optional skill `blender-mcp` (v2.1.0) documents `hermes mcp install blender`, then Blender addon install from [ahujasid/blender-mcp](https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py), then connect bridge each session. NousResearch social copy also surfaces the same one-liner.
- **Promo wave around Hermes + Blender MCP** — Julian Goldie SEO video [youtu.be/D4hk_D4VMCY](https://youtu.be/D4hk_D4VMCY) markets “imagination printer” / one-command setup and AI Profit Lab upsell. Install command matches official skill; addon + Blender-first connect steps are often under-explained in promo.
- **Separate Blender Foundation Lab MCP** — [blender.org/lab/mcp-server](https://www.blender.org/lab/mcp-server/) documents Blender’s own Lab MCP (Blender 5.1+, different addon/stack). Do not conflate with Hermes’s catalog `blender` entry (community blender-mcp bridge).
- **Community install chatter** — Termux single-script install posts, local/LM Studio demos, and “run free forever” YouTube titles. Treat as anecdotal; prefer official install + `hermes doctor`.
- **Fast-path messaging from Nous** — docs push `hermes setup --portal` (OAuth + Tool Gateway) as the fastest first-run path after install.

### Quotes / posts worth knowing

- Official docs: *“The self-improving AI agent built by Nous Research… not a coding copilot tethered to an IDE.”* — [docs home](https://hermes-agent.nousresearch.com/docs/)
- Blender MCP skill: *“Install the MCP server from the Nous catalog (one-time): `hermes mcp install blender`”* then addon + *“start Blender FIRST… Connect to Claude”* — [SKILL.md](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/optional-skills/creative/blender-mcp/SKILL.md)
- NousResearch (X search snippet): *“Easily activate and install the Blender MCP by running `hermes mcp install blender`…”* — [x.com/NousResearch](https://x.com/NousResearch)
- Promo (verify only): Goldie claims Blender/MCP/install are free; tokens are the paid layer — aligns directionally with OSS Hermes + paid model APIs, but “free API inside Hermes” claims need provider-specific verification.

### Implications for the research question

1. **Setup guide should lead with official Nous install docs**, not YouTube. Exact commands are public and stable on the docs site.
2. **Blender MCP is a multi-step stack**: catalog MCP install ≠ full readiness. Addon + live Blender bridge each session are required per official skill.
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
