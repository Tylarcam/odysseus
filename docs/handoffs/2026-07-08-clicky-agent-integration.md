# Handoff: Teach the Odysseus agent about Clicky + CMD Center

**Date:** 2026-07-08 · **Author:** Fable 5 (validation + spec) · **Builder:** Opus 4.8 or Sonnet
**Status:** validated — every file:line anchor below was re-verified against the working tree on this date.

---

## 1. Validation verdict

The in-app agent's diagnosis is **correct on all five claims**:

| # | Claim | Verified at |
|---|-------|-------------|
| 1 | Agent domain rules never mention Clicky/CMD Center | `src/agent_loop.py:134` (panel rule), `:460` (ui_control section) |
| 2 | `ui_control open_panel` whitelist rejects cmd-center/vault | `src/ai_interaction.py:1494-1537` (`_panel_aliases`) |
| 3 | `/clicky` is a user-only slash command | `static/js/slashCommands.js:6379-6384` → `_cmdStartClicky` → `clickyLaunch.js` |
| 4 | `app_api` cheat sheet omits Clicky endpoints | `src/agent_loop.py:472-501` |
| 5 | Start Clicky button is server-defined, invisible to agent | `services/home/cmd_center.py` (Ops group), handled in `static/js/cmdCenter.js:1046` |

Two facts the diagnosis left unstated, now pinned down:

- The frontend `open_panel` dispatcher is **`static/js/chatStream.js:145-183`** — that is where the cmd-center branch goes.
- `cmdCenter.js` already exports **`openCmdCenter()`** (async, line 1249) — the frontend fix is a dynamic import + call, same pattern as the existing `cookbook` branch at `chatStream.js:167-171`.
- API contract confirmed: `POST /api/clicky/start` takes optional body `{"launch_app": bool}` (default `true`); `GET /api/clicky/status` exists (`routes/clicky_routes.py:18-33`).
- `ui_control` is in `ALWAYS_AVAILABLE` in `src/tool_index.py:61`, so panel-opening needs no RAG change; only **`app_api`'s** description needs `clicky` keywords so "start clicky" retrieves it.

## 2. Decisions made for the builder (do not re-litigate)

| Decision | Choice | Why |
|----------|--------|-----|
| New named tool (`start_clicky`) vs. `app_api` rule? | **`app_api` rule** | Route already exists and is not blocked; a named tool means touching `tool_schemas.py`, `tool_implementations.py`, `tool_execution.py`, `tool_index.py` for one POST. The repo's own `app_api` doc says it exists exactly for "UI buttons with no named tool". Smallest diff wins. |
| Where does the agent learn button location? | **Hardcode the answer in the domain rule** ("CMD Center → Command Deck → Ops → Start Clicky") | Cheaper and more reliable than teaching the agent to fetch/parse `GET /api/home/cmd-center`. The button moves rarely; a prompt string is a one-line fix when it does. |
| Panel canonical name | `cmd-center`, aliases `cmdcenter`, `cmd_center`, `command-center`, `commandcenter`, `vault` | Matches DOM/CSS ids (`cmd-center-*`) and the route `/cmd-center`; "vault" is the UI's own label (see `cmdCenter.js` minimize button aria-label). |
| Frontend open mechanism | dynamic `import('./cmdCenter.js')` → `openCmdCenter()` | Identical to every other branch in the dispatcher; no eager import cost. |

## 3. Solution diagram

```
User (Agent mode): "start clicky" / "open the cmd center" / "where's the button?"
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ src/agent_loop.py                                     [EDIT 1]    │
│  • new domain rule: clicky → app_api; cmd-center → ui_control     │
│  • ui_control TOOL_SECTIONS entry: + cmd-center/vault panel       │
│  • app_api "common surfaces": + /api/clicky/*, /api/home/cmd-center│
└───────┬──────────────────────────────────────┬────────────────────┘
        │ (RAG retrieval of app_api needs      │
        │  "clicky" keyword)                   │
        ▼                                      ▼
┌────────────────────┐        ┌────────────────────────────────────┐
│ src/tool_index.py  │        │ PATH A: open the panel             │
│        [EDIT 2]    │        │ ui_control "open_panel cmd-center" │
│ app_api desc +=    │        │  → src/ai_interaction.py           │
│ clicky/cmd-center/ │        │    _panel_aliases        [EDIT 3]  │
│ vault keywords     │        │  → ui_event {panel:"cmd-center"}   │
└────────────────────┘        │  → static/js/chatStream.js:145     │
                              │    new branch            [EDIT 4]  │
┌────────────────────────────┐│  → import('./cmdCenter.js')        │
│ PATH B: launch Clicky      ││    .openCmdCenter()   (unchanged)  │
│ app_api POST               │└────────────────────────────────────┘
│  /api/clicky/start         │
│  {"launch_app": true}      │   UNCHANGED: routes/clicky_routes.py,
│ status: GET                │   services/clicky_launcher.py,
│  /api/clicky/status        │   services/home/cmd_center.py,
│ (routes already exist)     │   static/js/slashCommands.js
└────────────────────────────┘
```

## 4. The handoff prompt (paste everything below into the builder session)

---

You are working in `C:\Users\tylar\code\odysseus`. Read the project CLAUDE.md rules first. This task has been fully specified and validated — do not redesign it; implement exactly the edits below. Work in phases; after each phase run the verification for that phase and report results before continuing.

**Goal:** The in-app Odysseus agent (Agent mode) currently can't launch Clicky or open the CMD Center panel because its instruction files never mention them. You will add the instructions and one panel alias + one frontend dispatch branch. The Clicky API routes and UI already exist and work — you are wiring the agent's knowledge only.

**Hard constraints (anti-goals):**
- Do NOT create a new named tool. No changes to `tool_schemas.py`, `tool_implementations.py`, `tool_execution.py`.
- Do NOT touch `routes/clicky_routes.py`, `services/clicky_launcher.py`, `services/home/cmd_center.py`, `static/js/slashCommands.js`, `static/js/cmdCenter.js`.
- Append/insert only — do not reorder, reword, or refactor existing rules or aliases.
- Match the surrounding style exactly (these are prompt-text string blocks; keep the same bullet/formatting conventions as neighboring lines).

### Phase 1 — backend instruction files (3 files)

**1a. `src/ai_interaction.py`** — in the `open_panel` handler (`elif action == "open_panel":` around line 1494), add to the `_panel_aliases` dict, after the `"serving": "cookbook",` entry:

```python
            "cmd-center": "cmd-center",
            "cmdcenter": "cmd-center",
            "cmd_center": "cmd-center",
            "command-center": "cmd-center",
            "commandcenter": "cmd-center",
            "vault": "cmd-center",
```

Also update the error string on the `if not target:` branch to end with `..., settings, cookbook, cmd-center.` and add `cmd-center/vault` to the comment above the dict.

**1b. `src/agent_loop.py`** — three edits:

- In the domain-rules block, find the bullet starting `- "Open/show <panel>"` (around line 134). Add `cmd-center` to the parenthesized panel list and add these aliases to the alias run: `vault/command center/cmd center→cmd-center`.
- Immediately after that bullet, add a new bullet:

```
- "Start/launch/run Clicky" / "clicky overlay" → call `app_api` with `{"action":"call","method":"POST","path":"/api/clicky/start","body":{"launch_app":true}}`. "Is Clicky running" / "clicky status" → `GET /api/clicky/status`. "Where is the Clicky button" → tell the user: CMD Center (vault) → right rail → Command Deck → Ops group → **Start Clicky**, or type `/clicky` in chat; offer to open the panel via `ui_control` `open_panel cmd-center`. Clicky is the cursor-overlay app (Odysseus worker + Windows WPF overlay) — NOT a note, task, or model.
```

- In `TOOL_SECTIONS`: (i) in the `"ui_control"` entry (around line 460), add `cmd-center` to both parenthesized panel lists and mention the `vault` alias; (ii) in the `"app_api"` entry's **Common surfaces** list (around line 480–495), add one line:

```
- Clicky (cursor overlay): POST `/api/clicky/start` (body `{"launch_app": true}`), `GET /api/clicky/status`. CMD Center dashboard data: `GET /api/home/cmd-center`.
```

**1c. `src/tool_index.py`** — find the `app_api` description entry in the tool-description dict and append keywords so RAG retrieval surfaces it for Clicky asks, e.g. append: `Also the path for Clicky cursor-overlay launch/status (/api/clicky/start, /api/clicky/status) and CMD Center / vault dashboard data.` Do the same kind of append for the `ui_control` description if it enumerates panels.

**Phase 1 verification:** `python -c "import src.ai_interaction, src.agent_loop, src.tool_index"` must pass. Then grep your own diff: every occurrence of `cmd-center` you added must be lowercase-hyphenated. Run any existing tests that cover `open_panel` (grep `tests/` for `open_panel`) and add two cases: `open_panel cmd-center` and `open_panel vault` both return `{"ui_event": "open_panel", "panel": "cmd-center", ...}`, and an unknown panel's error message now lists `cmd-center`. Run those tests. Report results, then stop for approval.

### Phase 2 — frontend dispatcher (1 file)

**2a. `static/js/chatStream.js`** — in the `open_panel` handler (line 145–183), after the `notes` branch and before the `memories/skills/settings` branch, add:

```js
      } else if (panel === 'cmd-center') {
        import('./cmdCenter.js').then(function(mod) {
          var fn = mod.openCmdCenter || (mod.default && mod.default.openCmdCenter);
          if (fn) fn();
        }).catch(function(){});
```

(`openCmdCenter` is exported at `cmdCenter.js:1249`; follow the exact style of the `cookbook` branch above it.)

**Phase 2 verification:** `node --check static/js/chatStream.js`. No ESLint is configured for this repo — state that rather than claiming lint passed.

### Phase 3 — end-to-end verification

1. Restart the Odysseus server (required — `app_api` endpoint discovery reads live OpenAPI, and the running process predates the clicky routes in some environments).
2. In Agent mode ask: **"open the cmd center"** → CMD Center panel must open (no "Unknown panel" error).
3. Ask: **"start clicky"** → agent must call `app_api` POST `/api/clicky/start` (not shell, not a note, not web search) and report launcher output.
4. Ask: **"where is the start clicky button?"** → answer must name CMD Center → Command Deck → Ops → Start Clicky and/or `/clicky`.
5. Run the full test files you touched with pytest and paste the output.

**Acceptance criteria (all must hold):**
- [ ] `open_panel cmd-center` and `open_panel vault` resolve to panel `cmd-center` (unit-tested)
- [ ] Unknown-panel error message lists `cmd-center`
- [ ] chatStream.js dispatches `cmd-center` → `openCmdCenter()`
- [ ] Domain rule + app_api surfaces + ui_control section all mention Clicky/CMD Center
- [ ] `tool_index.py` app_api description contains "clicky"
- [ ] All three end-to-end asks in Phase 3 behave as specified
- [ ] Diff touches ONLY: `src/ai_interaction.py`, `src/agent_loop.py`, `src/tool_index.py`, `static/js/chatStream.js`, plus test files

---

## 5. Prompt-craft notes (why the handoff is shaped this way)

Written for reuse — this is the method, not just this instance.

1. **Verify before you delegate.** Every file:line in the source diagnosis was re-anchored with Grep/Read before it entered the prompt. A weaker model given a stale line number will "fix" the wrong place or burn context searching. Validation cost ~6 tool calls; a derailed builder session costs far more.
2. **Close every open contract.** The diagnosis said "add a frontend handler" without naming the file. The handoff instead names `chatStream.js:145`, the export to call (`openCmdCenter`, line 1249), and the neighboring branch to copy. A less capable model executes patterns well and designs them poorly — so the prompt supplies the pattern (the `cookbook` branch) and reduces the task to imitation.
3. **Make the design decisions up front and mark them non-negotiable.** "No new named tool" is stated as a hard constraint with the reasoning already recorded in §2, so the builder can't wander into a 6-file tool registration. Anti-goals (files NOT to touch) are as load-bearing as goals.
4. **Phase with checkpoints matching the project's own CLAUDE.md** (≤5 files/phase, verify, wait for approval). Each phase ends with a mechanical verification the builder can run without judgment: import check, `node --check`, named pytest cases.
5. **Acceptance criteria as a checklist, including a diff-surface criterion.** "Diff touches ONLY these files" is the cheapest guard against scope creep by an eager model.
6. **Provide exact payloads, not descriptions.** The domain-rule bullet and JS branch are given verbatim. For prompt-text files like `agent_loop.py`, wording *is* behavior — paraphrase by the builder would change the product.
7. **Anticipate the environmental gotcha.** The restart requirement (OpenAPI discovery) is stated in Phase 3 so a failing e2e check doesn't get misdiagnosed as a code bug.

**Tool decisions made during validation** (what I used and why):
- `Grep` with `-n`/`-C` to re-anchor every claimed line number — never trusted the pasted excerpt.
- `Read` on narrow offsets (~50–80 lines) around each anchor instead of whole files (agent_loop.py and ai_interaction.py are 1500+ lines).
- Parallel independent tool calls per round (3–4 at a time) — validation took 4 rounds.
- No subagents: the search space was 8 known files; fan-out would have cost more context than it saved.
