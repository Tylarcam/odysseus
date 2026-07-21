# Perplexity Agent Loop Factory — Research Brief

**Date:** 2026-07-09  
**Source:** Firecrawl agents (4) + Odysseus report `rp-ec0e573a080a`  
**Goal:** Ground a Perplexity-backed agent-loop factory for Odysseus

Raw agent payloads: `docs/research/firecrawl-agents-perplexity-factory/`

---

## Verdict (what to build)

**v1 factory = thin config + run harness over Agent API**, not a local SaC reimplementation.

| Layer | Own it? | Why |
|-------|---------|-----|
| Preset / instructions / max_steps / tools | Yes | Documented request fields |
| Outer loop (plan → run → critique → deepen) | Optional v1.5 | Client-owned; Agent already loops internally via `max_steps` |
| SaC primitives (`sdk.search.web`, etc.) | No | Internal to Perplexity sandbox only |
| Custom `SKILL.md` upload | Unclear | Skills load via sandbox `load_skill()` on `xhigh`; no clear “attach file to request” API |

Odysseus today (`src/perplexity_agent.py`) posts `{preset, input}` only. Official surface is much richer — and **preset names changed**.

---

## Critical API facts (Agent 1)

**Endpoint:** `POST https://api.perplexity.ai/v1/agent` (alias `/v1/responses`)

**Presets (current):**

| Preset | Formerly | Role | max_steps (typical) |
|--------|----------|------|---------------------|
| `fast` | — | Single-fact / quick | 1 |
| `low` | `pro-search` | Everyday research | ~5 |
| `medium` | `deep-research` | Multi-hop / wide | ~10 |
| `high` | `advanced-deep-research` | Exhaustive | ~15 |
| `xhigh` | — | Agentic + sandbox | up to 100 |

**Request knobs that matter for a factory:**

- `input` (string or message array) — multi-turn by client-supplied history  
- `preset` **or** `model` / `models` (fallback chain, max 5)  
- `instructions` — replaces preset system prompt when set  
- `tools` — `web_search`, `fetch_url`, `finance_search`, `people_search`, `sandbox`, `function`, `mcp`  
- `max_steps`, `max_output_tokens`, `reasoning.effort`  
- `stream: true` — SSE (`response.reasoning.search_queries`, `search_results`, text deltas, etc.)  
- `response_format` — structured JSON schema  

**Cost fields:** `usage.cost.total_cost` (+ input/output/tool/cache breakdown)

**Gap vs Odysseus:** default preset `deep-research` / setting `pro-search` may be **legacy aliases** — confirm whether API still accepts them or only `low`/`medium`.

---

## Search as Code (Agent 2)

- SaC = model writes Python that composes search primitives **inside Perplexity’s sandbox**.  
- SDK is **not** downloadable / not callable from Odysseus code.  
- Developers do **not** write SaC scripts; the model does.  
- Claimed ~85% token reduction on some wide-research benchmarks (task-dependent).  
- **Factory implication:** wrap Agent API (especially `medium`/`high`/`xhigh`) as a backend; if you need programmable search you control, reimplement with Firecrawl + local loop — don’t expect to import Perplexity’s SDK.

---

## Skills & prompting (Agent 3)

- Official skills: `SKILL.md` &lt; ~2000 tokens, few-shot composition patterns; tuned by Perplexity’s **internal** autoresearch loops.  
- Agent API: skills appear tied to **sandbox** (`load_skill({'name': ...})`), especially `xhigh` + `pplx_sdk`.  
- “AGENT framework” (Act/Ground/…) from the Deep Research report looks **third-party / marketing**; official architecture is SaC + presets + prompt guide docs.  
- softaworks/agent-toolkit Perplexity skill = Claude-Code MCP guide, **not** Perplexity Computer skills.  
- **Factory implication:** Odysseus “skills” should be **prompt/instruction packs + preset profiles** you attach via `instructions` / factory config — not assume uploadable Perplexity `SKILL.md` until proven.

---

## Pricing & orchestration (Agent 4)

- **API billing ≠ Pro/Max subscription.** Pay-as-you-go credits in API Console.  
- Pro’s $5/mo API credit: **discontinued / not in current official docs**.  
- Agent API: provider token rates (no markup) + tool fees (e.g. web_search ~$0.005/call, sandbox session fee).  
- Model Council & Perplexity Computer: **UI-only** (Max) — not factory backends.  
- Feasible patterns: model fallback chain, preset ladder, async batch + concurrency cap, domain filters, background poll for long jobs, client-side critique→requery.  
- Guardrails: `max_steps`, `max_output_tokens`, lean instructions, daily spend file (already in Odysseus), auto-reload on Perplexity side.

---

## Recommended factory shape (v1)

```text
PerplexityAgentSpec
  name: str                    # e.g. "job-enrichment", "academic-deep"
  preset: fast|low|medium|high|xhigh
  instructions: str            # domain playbook (Odysseus-owned)
  max_steps: int | None
  tools: list | None           # merge/override
  response_format: dict | None
  budget_usd_cap: float | None # per-run hard stop after response

factory.create(spec) -> AgentHandle
handle.run(query, *, history=None, stream_cb=None) -> ParsedReport
```

**Map to existing code:**

1. Extend `run_deep_research` → accept full payload knobs + stream.  
2. Add preset alias map: `pro-search→low`, `deep-research→medium`.  
3. Add `PerplexityAgentFactory` / registry of named specs (JSON or Python).  
4. Wire Deep Research sidebar to stream SSE events when `stream=true`.  
5. Keep IterResearch as fallback when budget / key / Agent failure.

**Do not build in v1:** local SaC SDK clone, Model Council clone, custom skill upload to Perplexity.

---

## Open questions (still need product answers)

1. Factory product: named one-shot specs (A) vs Odysseus outer critique loop (B)?  
2. First vertical: Deep Research sidebar, job pipeline, or chat `trigger_research`?  
3. Migrate settings off `pro-search`/`deep-research` strings now?  
4. Per-run `$` cap in addition to daily budget?

---

## Agent IDs (Firecrawl)

| # | Focus | ID |
|---|--------|-----|
| 1 | Agent API surface | `019f472c-48e8-7199-be99-493fe40d6781` |
| 2 | SaC / SDK | `019f472c-5506-7288-a35e-c222c6353a4f` |
| 3 | Skills / prompting | `019f472c-643e-72ff-b297-170c92839230` |
| 4 | Pricing / orchestration | `019f472c-64dd-7565-bad6-df9b0800e106` |
