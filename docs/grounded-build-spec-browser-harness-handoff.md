# Grounded Build Spec — Browser Harness Handoff (Odysseus)

> Status: Phase 1–3 implemented 2026-07-22. Dual-stack audited; `/reopen` pins `BU_CDP_URL`; tool copy steers Handshake to Path A.
> Audience: pickup agent (Cursor / Claude Code / Codex) continuing browser automation work.
> Conflict rule: where this spec contradicts code, **code wins for real names/values**; **spec wins for invariants**. File the conflict; do not improvise.

## 0. Reality check (claimed vs actual)

| Claimed gap | Actual state |
|-------------|--------------|
| "Browser harness isn't in Odysseus yet" | **False.** Two working paths exist: (A) external CLI `browser-harness` + (B) in-repo `browser_act` CDP operator. |
| "Need to build CDP attach from scratch" | **False.** `services/operator/cdp.py` (`CdpSession`) + `services/operator/browser.py` (`browser_act`) ship with tests in `tests/test_operator_browser.py`. |
| "Need Playwright MCP for browser work" | **False / forbidden for Handshake.** Prompts explicitly say use browser-harness + Comet CDP (`BU_CDP_URL=http://127.0.0.1:9333`), NOT Docker MCP Playwright. Playwright MCP remains an optional Admin preset only. |
| "One CDP port for everything" | **False / hazardous.** Operator defaults to `:9222` (`OPERATOR_CDP_PORT`). Handshake/Comet path uses `:9333` (`BU_CDP_URL`) because Lenovo Vantage occupies `:9222` on this machine. |
| "OpenSpec 'browser harness' = browser-use CLI" | **Naming collision.** OpenSpec `add-agentic-operator` calls the in-repo CDP tool a "browser harness service"; that is **`browser_act`**, not the `browser-harness` package. |
| "No reopen-from-memory" | **False.** `POST http://127.0.0.1:40001/reopen` opens tile URLs via CLI stdin `new_tab(...)`. |
| "No agent guidance for Handshake browser" | **False.** Duplicated in `src/job_pipeline/apply_queue.py`, `static/js/slashCommands.js`, `routes/agentmemory_routes.py`, `integrations/*/skills/handoff/SKILL.md`. |
| "Docs cover the dual stack" | **Partial gap.** `docs/archivist-external-deps.md` covers CLI + `/reopen`. Operator CDP + port split + when-to-use matrix were deferred (`openspec/.../tasks.md` 7.3). **This file closes that gap.** |
| "Daemon always up" | **Ops, not code.** `browser-harness --doctor` (2026-07-22): Chrome running OK; daemon not alive until first CLI call (`ensure_daemon()`). |

### Bugs / Day-1 fix-in-passing

1. **Stale OpenSpec checkbox** — `openspec/changes/add-agentic-operator/tasks.md` task 5.3 still `[~]` but `browser_act` is registered in `src/tool_schemas.py`, `src/tool_index.py`, `src/tool_implementations.py`, `src/tool_execution.py`, `src/agent_tools/__init__.py`. Mark `[x]` when touching that file.
2. **`/reopen` BU_CDP_URL pin** — **Fixed (Phase 2).** `browser_harness_env()` always sets `BU_CDP_URL` (process env → `memory_stack.env` → `http://127.0.0.1:9333`).
3. **browser-harness update lag** — doctor reports `0.1.0 (git)` vs latest `0.1.7`. Not a blocker; run `browser-harness --update -y` when the worktree is clean.

---

## Decision matrix (pickup agent: read this first)

| Situation | Use | Endpoint / command | Port / env |
|-----------|-----|--------------------|------------|
| Handshake apply, Comet login cookies, screenshot→click_at_xy flows | **A — browser-harness CLI** (outside Odysseus process) | `browser-harness <<'PY' ... PY` | `BU_CDP_URL=http://127.0.0.1:9333` (Comet) |
| Odysseus chat: "what tabs do I have?", "click login on this page" | **B — `browser_act` tool** | Agent tool `browser_act` | `OPERATOR_CDP_URL` or `OPERATOR_CDP_PORT=9222` (Chrome with remote debugging) |
| Re-open a Screenpipe/PixelRAG tile URL | **A via API** | `POST :40001/reopen` `{"article_id": N}` | Same as A (harness `.env`) |
| Headless scrape / optional MCP experiment | **C — Playwright MCP** | Admin preset `@playwright/mcp@latest --headless` | Own Chromium — **do not use for Handshake** |
| Auth wall / OTP | Stop; user finishes in Comet; continue | — | Never type credentials from screenshots |
| Submit Application on Handshake | Human only | — | Auto-submit forbidden |

**Invariant:** Do not unify A and B into one process in Phase 1–2. They intentionally target different browsers/ports and different trust models (CLI agent workspace vs consent-gated operator).

---

## Path A — External `browser-harness` CLI (working)

### (a) Design

- **Install:** editable checkout at `C:\Users\tylar\code\browser-harness`; on PATH as `C:\Users\tylar\.local\bin\browser-harness.exe`.
- **Skill:** `C:\Users\tylar\.claude\skills\browser-harness\SKILL.md` (and repo `SKILL.md` / `install.md`).
- **Daemon:** auto-started by `run.py` → `ensure_daemon()`. IPC namespaced by `BU_NAME` (default `default`). Windows: TCP loopback + port file.
- **CDP discovery order (daemon):** `BU_CDP_WS` → `BU_CDP_URL` (HTTP → resolve via `/json/version`) → probe `9222`/`9223` → profile discovery (includes Comet paths).
- **This machine's Comet config** (`browser-harness/agent-workspace/.env`):

```env
# Comet browser CDP endpoint (port 9333 avoids Lenovo Vantage on 9222).
# Comet must be launched with: comet.exe --remote-debugging-port=9333 --user-data-dir="%LOCALAPPDATA%\Perplexity\Comet\User Data"
BU_CDP_URL=http://127.0.0.1:9333
```

- **Preferred interaction style (skill):** `new_tab(url)` first (never clobber active tab with `goto_url`); `wait_for_load()`; `capture_screenshot()` → `click_at_xy(x,y)` → re-screenshot; DOM/`js(...)` only when no visible geometry; raw `cdp("Domain.method", ...)`.
- **Core helpers (pre-imported):** `new_tab`, `goto_url`, `page_info`, `wait_for_load`, `ensure_real_tab`, `capture_screenshot`, `click_at_xy`, `http_get`, `cdp`, plus remote: `start_remote_daemon`, `list_cloud_profiles`, `sync_local_profile` (needs `BROWSER_USE_API_KEY`).
- **Domain skills:** off unless `BH_DOMAIN_SKILLS=1`.

### (b) Implementation — Odysseus touchpoints

**Exists (do not rebuild):**

| File | What |
|------|------|
| `tools/unified_memory_api.py` | `open_url_via_browser_harness(url)` — stdin `new_tab(url!r)\nprint("opened")\n`, timeout **30s**, `check=True` |
| same | `POST /reopen` — body `{article_id: int}`; statuses 200/400/404/422/503 |
| `tests/test_reopen.py` | 7 tests (lookup, URL gate, 200/404/422/503) |
| `src/job_pipeline/apply_queue.py` | `compose_handshake_apply_message()` rule string for Comet CDP |
| `static/js/slashCommands.js` | same rule (~L1873) |
| `routes/agentmemory_routes.py` | AgentMemory remember payload concepts include `browser-harness`, `comet-cdp` |
| `docs/archivist-external-deps.md` | install + `/reopen` contract |
| `integrations/claude/skills/handoff/SKILL.md` | Handshake browser line |
| `integrations/codex/skills/handoff/SKILL.md` | same |

**`POST /reopen` contract (verbatim):**

```text
Request:  POST /reopen  JSON {"article_id": <int>}
200: {"status":"opened","article_id":N,"url":"...","window_title":...,"timestamp":...,"method":"browser-harness"}
400: {"error":"article_id required"|"invalid article_id"|"invalid json"|"invalid body"}
404: {"error":"article not found"}
422: {"error":"no openable url"}   # empty or non-http(s)
503: {"error":"browser-harness unavailable"}
```

URL gate: `is_openable_url` → must start with `http://` or `https://` after strip.

Metadata: `lookup_article_metadata(article_id)` keys `tiles_metadata.json` by **`str(article_id)` only**; fields used: `url`, `window_title`, `timestamp`. Path from `TILES_METADATA_PATH` in `memory_stack.env` (default `./data/archivist/tiles_metadata.json`).

**Done (Phase 2):** `browser_harness_env()` + `env=` on `subprocess.run`; `BU_CDP_URL` in `memory_stack.env`; tests in `tests/test_reopen.py`.

### (c) First test case

Already exists — extend only if Phase 2 env pin lands:

```python
# tests/test_reopen.py — prove subprocess receives BU_CDP_URL when pin is implemented
def test_open_url_sets_bu_cdp_url(monkeypatch):
    seen = {}
    def fake_run(cmd, **kwargs):
        seen["env"] = kwargs.get("env") or {}
        class R: returncode = 0
        return R()
    monkeypatch.setattr("tools.unified_memory_api.subprocess.run", fake_run)
    monkeypatch.setattr("tools.unified_memory_api.shutil.which", lambda _: "browser-harness")
    from tools.unified_memory_api import open_url_via_browser_harness
    open_url_via_browser_harness("https://example.com")
    assert seen["env"].get("BU_CDP_URL") == "http://127.0.0.1:9333"
```

Gate: `pytest tests/test_reopen.py -q`

---

## Path B — In-repo `browser_act` (working)

### (a) Design

- **Capability string:** `CAP_BROWSER_ACTION = "browser_action"`.
- **Actions:**
  - Read (ungated): `tabs`, `snapshot`
  - Mutating (consent): `navigate`, `click`, `type`, `evaluate`
- **Consent:** process-local `_consents[session_id]` TTL `CONSENT_TTL_SECONDS = 12 * 3600`. Grant when `user_approved is True`. Shared with `desktop_act`. Denial → `reason="consent_required"` + ask_user hint.
- **Envelope shape:**

```python
{"ok": bool, "capability": "browser_action", "data": Any, "degraded": bool,
 # optional: "reason", "hint"}
```

- **Degradation reasons:** `cdp_unreachable`, `no_ws_url`, `cdp_error: ...`, plus action errors: `unknown_action`, `no_open_tab`, `url_required`, `selector_required`, `expression_required`, `element_not_found`, `navigation_failed: ...`, `consent_required`.
- **Hint constant:** `"Start Chrome with --remote-debugging-port=9222 (close existing Chrome first)."`
- **CDP URL resolution** (`services/operator/core.py::cdp_url`):
  1. `OPERATOR_CDP_URL` if set (strip trailing `/`)
  2. else `http://127.0.0.1:{OPERATOR_CDP_PORT|9222}`
- **Probe:** `GET {cdp_url}/json/version` — available if body has `Browser`. Cache TTL `STATUS_CACHE_TTL = 30.0`.
- **Targets:** `GET {cdp_url}/json/list`, filter `type == "page"`. Default target = first page unless `target_id`.
- **Snapshot:** up to **200** interactive nodes (`a,button,input,textarea,select,[role=button],[role=link],[onclick]`), refs `n0`…`nN`, text slice **80** chars, visibility via `getBoundingClientRect`.
- **Click/type:** CSS `selector` or snapshot `ref` (`n12` → resolve to `#id` or tag). Uses `Runtime.evaluate` + `el.click()` / value set + input/change events — **not** compositor `click_at_xy` (that's Path A).
- **Audit table `operator_audit`:**

| column | type | notes |
|--------|------|-------|
| `id` | String PK | uuid hex |
| `timestamp` | DateTime | utcnow_naive |
| `capability` | String | `browser_action` \| `desktop_action` |
| `action` | String | e.g. `navigate`, `click` |
| `target` | Text | URL / selector / expression[:200] |
| `session_id` | String nullable indexed | |
| `result` | String | `ok` \| `error` \| `denied` |

- **Tool schema** (`src/tool_schemas.py`): name `browser_act`; params `action` enum + `target_id`, `url`, `selector`, `ref`, `text`, `expression`, `user_approved`.
- **Intent routing** (`src/tool_index.py`): phrases like `"my browser"`, `"open tabs"`, `"navigate to"`, `"fill in the form"` → `{"browser_act"}`.

### (b) Implementation

**Exists:**

| File | Role |
|------|------|
| `services/operator/browser.py` | `browser_act(args, session_id)` |
| `services/operator/cdp.py` | `CdpSession.command(method, params)` |
| `services/operator/core.py` | envelopes, consent, `cdp_url`, probes, audit |
| `src/tool_implementations.py` | `async def do_browser_act` → `asyncio.to_thread(browser_act, ...)` |
| `src/tool_execution.py` | dispatch `elif tool == "browser_act"` |
| `src/tool_schemas.py` / `tool_index.py` / `agent_tools/__init__.py` | registration |
| `tests/test_operator_browser.py` | codec, consent, degradation, registration |
| `scripts/operator_demo.py` | live smoke against Chrome :9222 |
| `memory_stack.env` | `OPERATOR_CDP_PORT=9222` |
| `openspec/changes/add-agentic-operator/specs/browser-action/spec.md` | normative SHALL |

**Done (Phase 3):** `browser_act` descriptions in `src/tool_schemas.py` + `src/tool_index.py` steer Handshake/Comet to Path A; comment pointer in `src/job_pipeline/apply_queue.py`. Consent invariants unchanged.

### (c) First test case

```bash
pytest tests/test_operator_browser.py -q
```

Live smoke (Chrome already on 9222):

```bash
python scripts/operator_demo.py
```

---

## Path C — Playwright MCP (optional, non-preferred)

### (a) Design

- Admin preset name: `"Browser (Playwright)"`
- Command: `npx`, args: `["-y", "@playwright/mcp@latest", "--headless"]`
- Settings category: tools matching `/^browser_|^close_session$/i` → label `Playwright`
- Install hint on failure (`src/mcp_manager.py`): run `npx -y @playwright/mcp@latest --version` once to cache package

### (b) Implementation

**Exists:** `static/js/admin.js` preset; `src/mcp_manager.py` connection error hint.

**New:** none. **Do not** wire Handshake to this path.

### (c) First test case

```bash
pytest tests/test_mcp_manager.py::test_playwright_mcp_connection_error_includes_install_hint -q
```

---

## Section: Handoff packet (what to paste to the next agent)

### (a) Design

Pickup agents must receive a fixed packet so they do not rediscover the dual stack. Packet fields:

```json
{
  "paths": {
    "A_cli": {
      "repo": "C:\\Users\\tylar\\code\\browser-harness",
      "bin": "browser-harness",
      "env_file": "C:\\Users\\tylar\\code\\browser-harness\\agent-workspace\\.env",
      "bu_cdp_url": "http://127.0.0.1:9333",
      "browser": "Comet",
      "launch": "comet.exe --remote-debugging-port=9333 --user-data-dir=%LOCALAPPDATA%\\Perplexity\\Comet\\User Data"
    },
    "B_operator": {
      "tool": "browser_act",
      "modules": ["services/operator/browser.py", "services/operator/cdp.py"],
      "env": "OPERATOR_CDP_PORT=9222 or OPERATOR_CDP_URL",
      "browser": "Chrome with --remote-debugging-port=9222"
    },
    "C_playwright_mcp": {
      "status": "optional_admin_only",
      "handshake": "forbidden"
    }
  },
  "odysseus_api": {
    "reopen": "POST http://127.0.0.1:40001/reopen",
    "operator_status": "GET /api/operator/status (if mounted)"
  },
  "tests": [
    "pytest tests/test_reopen.py -q",
    "pytest tests/test_operator_browser.py -q"
  ],
  "invariants": [
    "new_tab not goto_url for first navigation in Path A",
    "no auto-submit Handshake",
    "mutating browser_act requires user_approved after ask_user",
    "do not merge Path A and Path B ports without an explicit product decision"
  ]
}
```

### (b) Implementation

**New:** this file (`docs/grounded-build-spec-browser-harness-handoff.md`).

**Modify (Phase 1):** `docs/archivist-external-deps.md` — add a 10-line "Dual stack" pointer to this spec + Comet `:9333` note (do not duplicate full matrix).

**Modify (Phase 1):** mark OpenSpec task 5.3 `[x]` if editing that change folder.

### (c) First test case

Doc-level gate (no code):

```powershell
# Pickup smoke — agent must run before claiming browser work is broken
browser-harness --doctor
# Expect: chrome running OK; daemon may FAIL until first invoke
$env:BU_CDP_URL = "http://127.0.0.1:9333"
browser-harness <<'PY'
print(page_info())
PY
pytest tests/test_reopen.py tests/test_operator_browser.py -q
```

---

## Phase plan (≤5 files each; stop for approval between phases)

### Phase 1 — Handoff truth (docs only) — **this delivery**

Files (≤3):
1. `docs/grounded-build-spec-browser-harness-handoff.md` (this file)
2. `docs/archivist-external-deps.md` (pointer + Comet port note)
3. Optional: `openspec/changes/add-agentic-operator/tasks.md` (5.3 → `[x]`)

**Gate:** human reads Reality Check; agent can answer "which path for Handshake?" without grepping.

### Phase 2 — `/reopen` env pin (optional glue)

Files:
1. `tools/unified_memory_api.py`
2. `tests/test_reopen.py`
3. `memory_stack.env` (document `BU_CDP_URL` for reopen if desired)

**Gate:** `pytest tests/test_reopen.py -q` green; live `POST /reopen` opens tab in Comet when Comet listens on 9333.

### Phase 3 — Agent-facing routing copy

Files:
1. `src/tool_schemas.py` (`browser_act` description: "for Handshake/Comet use external browser-harness on 9333")
2. `src/tool_index.py` (same steer)
3. One of: `src/job_pipeline/apply_queue.py` / slashCommands (dedupe comment pointing to this doc)

**Gate:** unit tests still green; no behavior change.

### Phase 4 — Operator UI docs (deferred from OpenSpec 7.1/7.3)

Files later: `static/js/*` status panel + Graphy.md. Out of scope until Phase 1–3 approved.

**System-level definition of done:** An agent receiving only this doc + the handoff packet can (1) open a Handshake job in Comet via Path A, (2) list Chrome tabs via Path B `browser_act`, and (3) reopen a tile via `POST /reopen`, without installing Playwright or inventing a third CDP client.

---

## Operability clause

A weaker model can execute this because:

1. **No open design decisions** — Path A vs B vs C is fixed by the decision matrix; auto-submit remains forbidden.
2. **Exact files and symbols** are named (`browser_act`, `open_url_via_browser_harness`, `BU_CDP_URL`, `OPERATOR_CDP_PORT`, table `operator_audit`).
3. **Each phase ≤5 files** with an explicit pytest/doctor gate.
4. **Conflict rule:** code data wins; spec invariants win; file conflicts instead of merging ports or replacing Path A with Playwright.

**Deliberate overrides of naive requests:**

- Do **not** "simplify" to a single CDP port without confirming Lenovo Vantage is gone from `:9222`.
- Do **not** replace Comet+browser-harness Handshake with in-repo `browser_act` (different click model, different browser profile, no screenshot-first skill).
- Do **not** add a manager/retry/supervisor layer around the CLI (browser-harness design constraint).

---

## Quick reference — boot commands

```powershell
# Path A — Comet + harness
& "$env:LOCALAPPDATA\Perplexity\Comet\Application\comet.exe" `
  --remote-debugging-port=9333 `
  --user-data-dir="$env:LOCALAPPDATA\Perplexity\Comet\User Data"
$env:BU_CDP_URL = "http://127.0.0.1:9333"
browser-harness --doctor

# Path B — Chrome + Odysseus operator
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
# Odysseus app running; memory_stack.env has OPERATOR_CDP_PORT=9222
python scripts/operator_demo.py

# Path A via Odysseus API
python tools/unified_memory_api.py   # :40001
Invoke-RestMethod -Method POST -Uri http://localhost:40001/reopen `
  -ContentType application/json -Body '{"article_id": 0}'
```

## Related docs

- `docs/archivist-external-deps.md` — install matrix
- `docs/grounded-build-spec-personal-web-memory.md` — earlier note that browser-harness is an external dep
- `openspec/changes/add-agentic-operator/specs/browser-action/spec.md` — Path B SHALL
- `C:\Users\tylar\code\browser-harness\SKILL.md` + `install.md` — Path A usage
- `C:\Users\tylar\.claude\skills\browser-harness\SKILL.md` — Claude Code skill copy
