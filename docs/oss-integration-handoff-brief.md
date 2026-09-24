# Odysseus OSS Integration Handoff Brief

> **Audience:** Research / discovery agents that find open-source or vendor tools and must draft an **Odysseus-tailored integration handoff** (not a generic sample README, not a greenfield scaffold).
>
> **Repo context:** Odysseus monorepo · default branch `dev` · app entry `app.py` (FastAPI + static UI)
>
> **Related skills (humans / builder agents):** `oss-stack-integration`, `validated-handoff`, `grounded-build-spec`
>
> **Sensitivity:** This brief is architecture-only. Never paste secrets, live env values, hostnames, bind addresses, ports, credentials, personal filesystem paths, or deployment topology into handoffs derived from it.

---

## 1. Purpose

When a problem surfaces and research finds a candidate tool (search API, scraper, browser agent, OCR, vector DB, MCP server, etc.), your job is **not** to invent a demo integration.

Your job is to produce a handoff packet that:

1. Places the tool on the **correct Odysseus seam**
2. Names **exact files and patterns to copy** in this repo
3. Separates **IDE MCP** from **in-app runtime**
4. Ships the **highest-ROI Phase 1** only; defers the rest with reasons
5. Is executable by a weaker builder model without redesign

If the handoff could apply to any random FastAPI app unchanged, it is wrong. Re-ground it.

### Do not put in handoffs or this brief’s derivatives

- API keys, tokens, passwords, OAuth refresh material, or `.env` values
- Personal absolute paths (e.g. user home directories)
- Live hostnames, IPs, bind addresses, ports, reverse-proxy, or tunnel configs
- Private vendor account IDs, billing details, or rate-limit quotas tied to a real account
- Auth bypass notes, privilege-escalation ideas, or “how to disable safety checks”
- Internal infra runbooks unrelated to the code seam being extended

---

## 2. What Odysseus is (host context)

Odysseus is a **self-hosted AI workspace**: chat, agent tools, Deep Research, Cookbook (model fit/serve), Compare, documents, memory/skills, email, notes/tasks, calendar, voice/CMD Center, Clicky.

| Fact | Implication for integration |
|------|-----------------------------|
| Stack = **Python 3.11+ / FastAPI** + **static JS** (`static/`) | Prefer Python provider modules + Settings UI; do not assume a React SPA for core product |
| Local-first, privacy-first | Prefer self-hostable / key-in-settings; document data egress |
| Agent already has `web_search` / `web_fetch` | New search tools usually extend the **provider registry**, not a new agent tool |
| Deep Research ≠ Cookbook | Research is multi-step source synthesis; Cookbook is local model download/serve |
| MCP exists in-app **and** in Cursor/Claude | Dual auth paths (OAuth MCP vs app API key) — never conflate |

**Do not** treat `apps/story-canvas/` or one-off `.tmp/` orch folders as the primary product surface unless the problem is explicitly about those.

---

## 3. Decision tree (before drafting)

```
Candidate tool found
        │
        ├─ Does Odysseus already have an equivalent?
        │     YES → handoff = "use existing X" or "thin adapter", not full install
        │
        ├─ What primitive is the ROI?
        │     Search / Fetch / Agent-automation / Browser / Storage / Domain MCP / Other
        │
        ├─ Which host seam owns that primitive?  (see §4)
        │
        ├─ Phase 1 path: native provider | agent tool | MCP-only | research fan-out | defer
        │
        └─ Draft handoff with Odysseus file anchors + anti-goals + verify steps
```

**ROI default for web/search vendors:** ship **Search** (cheap, LLM-ready snippets) first. Defer metered Agent/Browser until an interactive/auth workflow is the actual ask.

---

## 4. Odysseus seams (where tools land)

Pick **one primary seam** for Phase 1. Name it explicitly in the handoff.

### A. Search provider (most common for OSS web tools)

| Piece | Path | Role |
|-------|------|------|
| Registry + impl | `services/search/providers.py` | `PROVIDER_INFO`, `*_search()`, key maps |
| Dispatch | `services/search/core.py` | `_call_provider`, `comprehensive_web_search` |
| Page fetch | `services/search/content.py` | Used by `web_fetch` — preserve existing URL safety checks |
| Settings defaults | `src/settings.py` | `DEFAULT_SETTINGS`, `search_provider`, `*_api_key` field names only |
| Settings UI | `static/js/settings.js`, `static/index.html` | Provider select, key fields, hints |
| Research override UI | `static/js/research/panel.js` | Optional discovery override |
| Selection search | `static/js/selectionSearch.js` | Own preference order — touch only if needed |
| Env docs | `.env.example` | Document variable *names* only; never commit values |
| Tests | `tests/test_*_search_provider.py` | Mirror `tests/test_tinyfish_search_provider.py` |

**Existing providers:** `searxng`, `brave`, `duckduckgo`, `google_pse`, `tavily`, `serper`, `firecrawl`, `tinyfish`, `perplexity`, `disabled`.

**Normalize results to:** `[{title, url, snippet, age?}]`. Do not leak vendor-only fields into callers unless the host already supports them.

**Inheritance:** Agent `web_search`, chat pre-search, and usually voice inherit the global `search_provider`. Prefer extending the provider over new tools.

### B. Agent tools (only when no provider seam fits)

| Piece | Path |
|-------|------|
| Handlers | `src/agent_tools/` (e.g. `web_tools.py`) |
| Registry | `src/agent_tools/__init__.py` (`TOOL_HANDLERS`, `TOOL_TAGS`) |
| Schemas | `src/tool_schemas.py` |
| Implementations | `src/tool_implementations.py` |
| Dispatch | `src/tool_execution.py` |
| RAG / always-on | `src/tool_index.py` |
| Allow-lists / policy | Existing modules under `src/tool_*.py` — extend carefully; do not weaken checks |
| Prompts | `src/agent_loop.py` |

New named tools are expensive. Prefer `app_api` or existing tools when a route already exists (see dated examples under `docs/handoffs/`).

### C. Deep research / operator fan-out

| Piece | Path |
|-------|------|
| Live research | `src/research_handler.py`, `src/deep_research.py` |
| Perplexity engine | `src/perplexity_agent.py` |
| Operator fan-out | `services/operator/research.py` (hardcoded provider set — **separate wiring**) |
| Routes / UI | `routes/research_routes.py`, `static/js/research/*` |

Offline Cursor “research-swarm” orch under `research-orch/` is **not** the in-app seam. Do not tell builders to “add a swarm leg” unless the user asked for orch workflow changes.

### D. MCP

| Path | Meaning |
|------|---------|
| `src/mcp_manager.py`, `src/builtin_mcp.py`, `mcp_servers/` | **In-app** MCP runtime |
| Cursor/Claude `mcp.json` / installer | **IDE** tools for the human + coding agent |

**Rule:** Search/fetch/shell/files usually stay **native**. MCP is for domain servers or IDE-side ad-hoc use. Document both enable steps when both matter; never assume MCP OAuth fills `*_API_KEY` in Odysseus settings.

### E. Side surfaces (usually inherit — do not over-wire)

| Surface | When to touch |
|---------|----------------|
| Voice / CMD Center | Only if that surface’s tool set must gain a capability (`services/voice/voice_tools.py`) |
| Clicky | Only if it needs a tool loop or pre-LLM inject; skip if shared search already feeds it |
| Story canvas | Only if the ask is canvas-specific (`routes/story_canvas_routes.py`, `apps/story-canvas/`) |
| Scheduled tasks | Only if scheduled jobs need the new capability (`src/task_scheduler.py`) |

---

## 5. Dual path: MCP vs native (mandatory section in every handoff)

Every candidate with both an MCP server and a REST/API must answer:

| Path | Auth | Lives in | Good for |
|------|------|----------|----------|
| **IDE MCP** | Usually OAuth | Cursor / Claude / Codex config | Ad-hoc research while coding |
| **Odysseus native** | API key in Settings / `.env` | `services/search` or agent tools | Chat agent, voice, research jobs |

Handoff must include **Enable app** and **Enable MCP** as separate checklists. State explicitly if Phase 1 is MCP-only, native-only, or both.

---

## 6. What the research agent must output

Produce one markdown artifact (suggested path: `docs/handoffs/YYYY-MM-DD-<vendor>-integration.md` or a research brief under `docs/research/`). Structure:

### A. Candidate fit card

| Field | Required |
|-------|----------|
| Problem it solves (user language) | Yes |
| Vendor / OSS name + license + primary docs URL | Yes |
| Primitive ladder (Search / Fetch / Agent / Browser / Other) | Yes |
| Cost / rate limits / self-host vs SaaS | Yes |
| Overlap with existing Odysseus providers/tools | Yes — name them |
| Recommended Phase 1 seam | Exactly one |
| Deferred surfaces | Named + why |

### B. Reality check (no invention)

Before recommending “add provider X”, confirm against the live tree:

- Is there already a provider / tool / MCP with the same job?
- Is the gap “missing capability” or “wrong default / missing key / UI not wired”?
- Cite **file paths** (verify in-session; do not trust stale line numbers from prior chats).

### C. Odysseus placement map (ASCII)

Show: user trigger → seam → files tagged `[EDIT n]` → what stays `UNCHANGED`. Mirror the structure of existing dated files under `docs/handoffs/`.

### D. Clone-this-pattern checklist

For **search providers**, Phase 1 file budget (≤5 files preferred):

1. `services/search/providers.py` — `PROVIDER_INFO` + `*_search` + key map  
2. `services/search/core.py` — `_call_provider` branch  
3. `src/settings.py` — `DEFAULT_SETTINGS` key  
4. `static/js/settings.js` + `static/index.html` — UI (count as shared UI concern; split phase if over budget)  
5. `tests/test_<id>_search_provider.py` — request shape, empty-without-key, registry dispatch  

Optional later phases: `.env.example`, research panel options, `selectionSearch.js`, `services/operator/research.py` fan-out.

**Pattern to copy:** TinyFish — provider id `tinyfish`, settings field `tinyfish_api_key`, env *name* `TINYFISH_API_KEY` (never a value), test `tests/test_tinyfish_search_provider.py`. Skill detail: `oss-stack-integration` (+ its reference notes).

### E. Decisions table (non-negotiable for builder)

| Decision | Choice | Why |
|----------|--------|-----|
| Native vs MCP-first | … | … |
| New agent tool vs provider | … | … |
| Touch Clicky/voice? | No / Yes | … |
| New dependency? | Ask user first | Repo rule |

### F. Paste-ready builder prompt

Include:

1. Context + goal (one paragraph)  
2. Hard constraints / anti-goals (files **not** to touch)  
3. Phases ≤5 files each; stop for approval between phases  
4. Exact insert shapes or “copy function X, rename to Y” with verified anchors  
5. Mechanical verification per phase (`pytest` target, Settings Test button, MCP tools visible)  
6. Acceptance checklist including “diff touches ONLY these files”

### G. Enable / verify report stub

```markdown
## Integrated: <Vendor>
- ROI path: <Search provider | MCP | agent tool | both>
- Files touched: …
- Enable app: Settings → … or ENV=…
- Enable MCP: config path + OAuth steps
- Deferred: … — why
- Verify: pytest … / live Test / MCP tools visible
```

---

## 7. Execution rules for builders (embed in handoffs)

Pull these into every builder prompt; they match how this workspace ships code:

- PRs against **`dev`**; one concern per PR (`CONTRIBUTING.md`)
- **≤5 files per phase**; wait for human approval before the next phase
- **Ask before adding dependencies**
- Do not commit `.env` or secrets
- Prefer smallest diff; extend existing patterns; no parallel pipelines when `_call_provider` already exists
- Verification for this repo is primarily **`pytest`** / `python tests/run_focus.py` / `py_compile` / `node --check` — not `tsc`/`eslint` for the core app. State that explicitly so builders do not fake a typecheck pass
- Reference test pattern: `tests/test_tinyfish_search_provider.py`

---

## 8. Anti-patterns (reject in drafts)

- Generic “add an Express middleware” or “drop this into LangChain” samples
- Wiring Browser/Agent automation before Search works end-to-end
- Duplicating Firecrawl-style scrape when Search snippets suffice
- Putting keys only in MCP config and expecting Odysseus Settings to find them
- Touching Clicky / voice / CMD Center when the shared search provider already feeds those paths
- Treating `research-orch/` or `.tmp/` as production integration targets
- Recommending a new named agent tool when a provider registry entry is enough
- Inventing file paths — if unsure, say “verify path” and list the search command to run

---

## 9. Worked reference: TinyFish (canonical)

| Path | What | Auth |
|------|------|------|
| IDE MCP | Vendor MCP endpoint (see current TinyFish docs) | OAuth in the IDE client |
| Odysseus provider | `tinyfish` → vendor Search API | Settings field / env *name* only |

**ROI placement:** search (and optionally research discovery) provider. Agent/Browser metered APIs deferred until interactive workflows are required.

Use this as the template narrative: audit host → map primitives → Phase 1 native Search → optional MCP parallel track → report deferred surfaces.

---

## 10. Quick seam cheat sheet

| If the tool is mainly… | Phase 1 seam |
|------------------------|--------------|
| Web SERP / news / snippets | `services/search` provider |
| Page extract / crawl after URLs known | Extend fetch (`content.py`) or provider fetch; avoid new tool if `web_fetch` covers it |
| Multi-step “research report” | Deep research / operator — only after Search exists |
| Interactive login / click-through | Metered browser/agent — explicit ask; often defer |
| IDE-only ad-hoc browse while coding | Cursor MCP only |
| Email / memory / domain CRUD | In-app MCP server under `mcp_servers/` or native routes — audit first |
| Local model serve | Cookbook — usually **not** a web OSS weave |

---

## 11. Minimum quality bar before publishing the handoff

- [ ] Problem statement matches a real Odysseus user flow (chat agent, research, voice, etc.)
- [ ] Overlap check against existing `PROVIDER_INFO` / tools completed
- [ ] One primary Phase 1 seam named
- [ ] Exact files listed; pattern-to-copy named (e.g. TinyFish)
- [ ] MCP vs native auth split written
- [ ] Deferred list non-empty unless truly nothing to defer
- [ ] Builder prompt has anti-goals + phase gates + pytest target
- [ ] No secrets, personal paths, host/port/bind details, or live credentials
- [ ] `.env.example` / settings docs list variable *names* only

---

*This brief is the host-context contract for research agents. Implementation detail stays in `oss-stack-integration`; validation + paste-ready builder packaging stays in `validated-handoff`.*
