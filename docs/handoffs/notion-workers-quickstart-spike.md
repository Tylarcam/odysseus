## Spike scope

Validate [Notion Workers quickstart](https://developers.notion.com/workers/get-started/quickstart) on the **host machine** (Windows) before any Odysseus `manage_notion` / bridge code. This is a **read-only spike** relative to Odysseus mainline — do not modify MCP gateway, `admin.js` Notion preset, job pipeline, or agent tools.

## Why

- Docker Notion MCP (gateway `:8811`) works for **read/search** but cannot **create pages**.
- Notion's new platform adds **Workers** (hosted runtime) + **`ntn` CLI** for write/deploy/sync.
- Odysseus will eventually weave `ntn` like `gog` (`gmail_gog.py`), but only after we prove Workers deploy and `sayHello` exec on this machine.

## Prerequisites (verify first)

| Requirement | Check |
|-------------|-------|
| Node.js **≥ 22** | `node -v` |
| npm **≥ 10** | `npm -v` |
| Notion workspace | Business/Enterprise if Workers beta requires admin enable |
| Network | `curl -fsSL https://ntn.dev` reachable |

## Test procedure (follow quickstart exactly)

Reference: https://developers.notion.com/workers/get-started/quickstart

### 1. Install CLI

```powershell
curl -fsSL https://ntn.dev | bash
# or on Windows if bash unavailable, use official install path from Notion docs
ntn --version
```

### 2. Scaffold worker (outside Odysseus repo)

Use a **scratch directory**, not `odysseus/` root:

```powershell
mkdir C:\Users\tylar\code\notion-workers-spike -Force
cd C:\Users\tylar\code\notion-workers-spike
ntn workers new odysseus-spike-test
cd odysseus-spike-test
```

### 3. Inspect scaffold

Confirm `src/index.ts` exports a `Worker` with sample `sayHello` tool (per quickstart).

### 4. Deploy

```powershell
ntn workers deploy
```

- Complete OAuth / workspace auth when prompted.
- Record workspace ID and worker name from `workers.json` if created.

### 5. Exec sample tool

```powershell
ntn workers exec sayHello -d '{"name": "Odysseus"}'
```

Expected: friendly greeting string returned.

### 6. Optional stretch (only if 1–5 pass)

```powershell
ntn workers list
ntn workers exec sayHello -d '{"name": "World"}' --local   # if supported
```

Skim next-step docs (do not implement yet):
- [Syncs](https://developers.notion.com/workers/guides/syncs)
- [Agent tools](https://developers.notion.com/workers/guides/tools)
- [Webhooks](https://developers.notion.com/workers/guides/webhooks)

## Success criteria

- [ ] `ntn` installs and authenticates
- [ ] `ntn workers deploy` succeeds without Odysseus running
- [ ] `ntn workers exec sayHello` returns expected output
- [ ] Notes captured: where auth tokens live, deploy path, any Windows-specific friction

## Failure capture

If any step fails, record in handoff completion:
- Exact command + stderr
- Node/npm versions
- Whether Workers are enabled in workspace admin
- Whether CLI auth completed

Do **not** patch Odysseus to work around failures yet.

## After spike (only if green)

1. Create git branch: `feat/notion-workers-bridge` from current `dev`
2. Add `integrations/notion-workers/` by moving/adapting the spike project
3. Phase A Odysseus work: `NOTION_BRIDGE_ENABLED=false` by default, `src/notion_ntn.py`, `manage_notion` tool — **separate PR**

## Odysseus integration context (for later, not this spike)

| Lane | Role |
|------|------|
| MCP (Docker gateway) | Read/search when user mentions Notion |
| `ntn` CLI | Page create/edit, worker deploy/sync from host |
| Workers | Persistent sync + tools calling `/api/codex/*` |

Existing MCP preset (`2022-06-28` in admin) stays untouched until bridge feature merges.

## Deliverable

Short spike report (markdown) with:
- Pass/fail per step
- Paths to spike project and auth config
- Recommendation: proceed to `feat/notion-workers-bridge` or blockers list
- Suggested first Worker tool for Odysseus bridge: `odysseusPing` → GET `/api/codex/capabilities`
