# Research Brief — Hermes Agent Setup (Step by Step)

| Field | Value |
|-------|-------|
| **Topic / question** | Hermes Agent setup — step by step: what it is, install, config, MCP/Blender, troubleshooting, cost, alternatives |
| **Audience / use** | Builder who wants to install Hermes Agent and wire Blender MCP / MCP tools into an agent stack (Cursor / Claude / Odysseus-adjacent) |
| **Category** | `howto` |
| **Session id** | `rp-hermes-agent-setup-20260716` |
| **Owner** | `tylarcam` |
| **Orch root** | `c:\Users\tylar\code\odysseus\research-orch\hermes-agent-setup-20260716` |
| **Date** | 2026-07-16 |

## Seed context (verify; do not treat as ground truth)

- YouTube promo: Julian Goldie SEO — Hermes Agent + Blender MCP (`https://youtu.be/D4hk_D4VMCY`). Transcript seed at `research-orch/hermes-blender-mcp-20260716/transcript.txt` (cites commands like `hermes mcp install blender`; treat as marketing until confirmed in official docs).
- Prior orch may cite AI Profit Lab / aiprofitborn.com — prefer **Nous Research official** sources over community upsell pages.

## Must-answer questions

1. What is Hermes Agent, and where is the official source (repo / docs site)?
2. Prerequisites (OS, Python/Node/runtime, accounts, API keys)?
3. Install steps (exact commands if documented)?
4. First-run / config (env, models, MCP enablement)?
5. How to install/enable Blender MCP if documented?
6. Common failures / troubleshooting?
7. Cost model (what's free vs paid — Hermes, Blender, MCP, model/API tokens)?
8. Alternatives / when not to use Hermes?

## Authority URLs (seed — expand via search)

| URL | Why |
|-----|-----|
| https://github.com/NousResearch/hermes-agent | Official repo |
| https://hermes-agent.nousresearch.com/docs/ | Official documentation |
| https://hermes-agent.nousresearch.com/docs/getting-started/installation | Installation guide |
| https://hermes-agent.nousresearch.com/docs/getting-started/quickstart | Quickstart |
| https://hermes-agent.nousresearch.com/docs/user-guide/configuration | Configuration |
| https://hermes-agent.nousresearch.com/docs/user-guide/desktop | Desktop app |
| https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md | MCP feature docs |
| https://github.com/NousResearch/hermes-agent/blob/main/optional-skills/creative/blender-mcp/SKILL.md | Blender MCP skill / setup |
| https://www.blender.org/lab/mcp-server/ | Blender Lab MCP server (related authority) |
| https://youtu.be/D4hk_D4VMCY | Promo seed only — verify claims |

Discover and prefer any install / quickstart / getting-started pages under the official docs site.

## Recency keywords (A1)

- Hermes Agent, NousResearch/hermes-agent, hermes-agent.nousresearch.com
- Blender MCP, `hermes mcp install blender`, blender-mcp skill
- Julian Goldie, AI Profit Lab / aiprofitborn (context only)
- MCP setup Hermes, Hermes Desktop installer

## Synthesis angle (A3)

Reconcile: (a) official Nous Research install + MCP + Blender skill docs, (b) recent community/promo claims about one-command Blender MCP install, (c) free vs paid layers (open-source Hermes/Blender vs model API cost). Produce a verified step-by-step setup path a builder can follow; flag unsourced promo claims.

## Legs (default trio)

- **A1** last30days / recency → `a1_last30days.md`
- **A2** Firecrawl authority scrape → `a2_firecrawl.md`
- **A3** Perplexity synthesis → `a3_perplexity.md` (+ raw JSON if available)

TinyFish / DeepAgents: deferred unless authority pages require browser automation.
