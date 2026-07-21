## A3 Perplexity Digest

*Engine: Docker MCP `perplexity_research` (fallback). Odysseus `POST /api/research/start` with `perplexity_agent` returned HTTP 403 (“API tokens must use a scope-aware API route”). Raw narrative saved as `a3_perplexity_raw.json` (text research output).*

### Findings (numbered, cited)

1. **Official product:** Hermes Agent by Nous Research — open-source self-improving agent. Canonical sources: [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) and [hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs/). ([Perplexity synthesis + Firecrawl-verified docs])

2. **Prerequisites:** Git (plus Linux curl/xz-utils); installer brings Python 3.11 (via uv), Node 22, ripgrep, ffmpeg. Model must support ≥64K context. ([Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation), [Quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart))

3. **Install commands (documented):**
   - Desktop: download from hermes-agent.nousresearch.com
   - Unix/WSL/Termux: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`
   - Windows PowerShell: `iex (irm https://hermes-agent.nousresearch.com/install.ps1)`
   - Then reload shell → `hermes`

4. **First-run:** Prefer `hermes setup --portal` (OAuth + Tool Gateway), else `hermes model` / Full Setup / Blank Slate. Secrets in `~/.hermes/.env`, settings in `config.yaml`. Verify with a plain chat before adding gateway/MCP/skills. ([Quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart))

5. **MCP enablement:** Included in standard install. Catalog: `hermes mcp` / `hermes mcp install <name>`. Or YAML `mcp_servers` for stdio/HTTP. Hermes can also `hermes mcp serve` for Cursor/Claude Code clients. ([MCP docs](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md))

6. **Blender MCP (official skill):** `hermes mcp install blender` → install ahujasid `addon.py` in Blender → enable Interface: Blender MCP → each session Connect bridge *before* Hermes. Tools: scene/object info, viewport screenshot, execute_blender_code. ([SKILL.md](https://github.com/NousResearch/hermes-agent/blob/main/optional-skills/creative/blender-mcp/SKILL.md))

7. **Promo reconciliation:** Julian Goldie video ([youtu.be/D4hk_D4VMCY](https://youtu.be/D4hk_D4VMCY)) correctly names `hermes mcp install blender` and free OSS layers, but underplays addon + Connect-each-session; “minutes per scene” / free API brand names are marketing, not docs guarantees.

8. **Troubleshooting:** PATH/`hermes: command not found`; API key/provider misconfig; dotenv when wrong launcher; MCP filter/connect failures; Blender connection refused if bridge not up; use `hermes doctor` recovery sequence. ([Installation troubleshooting](https://hermes-agent.nousresearch.com/docs/getting-started/installation), Quickstart common failures)

9. **Cost model:** Hermes + Blender + MCP software free/OSS. Paid: LLM tokens (Nous Portal tiers/credits, OpenRouter, Anthropic, etc.), optional infra (VPS/GPU). Tool Gateway bundled under Portal path. ([docs + Portal references in research])

10. **When not to use Hermes:** Need only IDE inline completion; want zero local/agent ops; intolerant of multi-step config; or prefer Blender Lab’s native MCP stack with a different LLM client rather than Hermes catalog blender-mcp.

### Contradictions / uncertainty

- **Two Blender MCP products:** Hermes catalog (`ahujasid/blender-mcp`, Blender 3.0+) vs Blender Lab MCP (Blender 5.1+). Promo rarely distinguishes.
- **“Free forever” YouTube titles** conflict with real token/Portal costs — software free ≠ inference free.
- **Odysseus perplexity_agent** unavailable in this run (403 scope); synthesis used Docker Perplexity + authority scrapes.
- Exact current Nous Portal dollar tiers not fully scraped here — check [portal.nousresearch.com](https://portal.nousresearch.com/) live.

### Implications

Builder path for Odysseus/Cursor-adjacent stacks: install Hermes CLI on Windows via `install.ps1` or Desktop → get chat working with Portal or BYO key → add MCP catalog entries → for Blender, follow skill’s three-step (mcp install + addon + Connect). Do not trust promo one-liners as complete setup. Wire other agents to Hermes messaging via `hermes mcp serve` if needed.

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
