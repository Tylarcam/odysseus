# AGENTS.md

## Cursor Cloud specific instructions

Odysseus is a single-service, self-hosted AI workspace: a FastAPI backend
(`app.py`) that serves a vanilla-JS front-end from `static/`. There is no
separate frontend build step — the JS is served as-is.

### Environment
- Python deps live in a local virtualenv at `./venv` (git-ignored). The update
  script keeps it in sync with `requirements.txt`. Always invoke tools through
  it, e.g. `./venv/bin/python`, `./venv/bin/pytest`.
- First-boot state (`data/` dir, SQLite DB at `data/app.db`, and the admin
  account in `data/auth.json`) is created by `python setup.py`. It is safe to
  re-run and skips anything that already exists.
- A dev admin account exists in the persisted snapshot: username `admin`,
  password `OdysseusDev123!`. If `data/` was wiped, re-run
  `ODYSSEUS_ADMIN_PASSWORD='OdysseusDev123!' ./venv/bin/python setup.py` to
  recreate it (otherwise setup prints a random temporary password).

### Run / test / lint (single service)
- Run (dev): `./venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 7000`
  then open `http://localhost:7000`. No `--reload` is required, but it works.
- Test: `./venv/bin/python -m pytest -q` (suite is ~3000 tests, ~75s).
- Lint/syntax (mirrors CI in `.github/workflows/ci.yml`):
  `./venv/bin/python -m compileall -q app.py core routes src services scripts tests`
  and `node --check` over `static/app.js static/js/**/*.js`.

### Non-obvious caveats
- ChromaDB is OPTIONAL. It is not bundled in the native run, so startup logs
  `ChromaDB is not reachable at localhost:8100` and vector memory / RAG /
  tool-index features run in a degraded keyword-fallback mode. This is expected
  and does not block startup or the core app. To enable full vector features,
  run a ChromaDB service on `localhost:8100` (e.g. `docker run -p 8100:8000
  chromadb/chroma`).
- No LLM provider is configured by default, so Chat/Agent/Deep-Research will not
  return completions until a provider is added in-app under **Settings** (or via
  `.env` `LLM_HOST` / `OPENAI_API_KEY`). Non-LLM features (Notes, Documents,
  Calendar, Tasks) work fully offline — use one of those for a quick smoke test.
- The built-in Browser MCP server is skipped unless `@playwright/mcp` is in the
  npx cache; the startup warning about it is harmless.
- `node_modules` / `npm install` are NOT needed to run or test the app; the
  `package.json` deps are optional dev tooling.
