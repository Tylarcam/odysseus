"""Env ODYSSEUS_API_TOKEN is accepted as the owner without a SQLite lookup."""

from pathlib import Path
from types import SimpleNamespace

from src.auth_helpers import (
    accept_env_api_token,
    effective_user,
    env_api_token_owner,
    match_env_api_token,
)


_ENV = "ody_" + ("A" * 43)
_WRONG = "ody_" + ("B" * 43)


def _mgr(owner="tylarcam"):
    return SimpleNamespace(users={owner: {"is_admin": True}})


def _req():
    return SimpleNamespace(state=SimpleNamespace())


def test_matching_env_token_sets_effective_user_owner(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_API_TOKEN", _ENV)
    req = _req()
    assert accept_env_api_token(req, _ENV, _mgr()) is True
    assert req.state.api_token is True
    assert req.state.current_user == "api"
    assert req.state.api_token_owner == "tylarcam"
    assert effective_user(req) == "tylarcam"


def test_wrong_token_is_rejected_as_invalid(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_API_TOKEN", _ENV)
    req = _req()
    assert match_env_api_token(_WRONG) is False
    assert accept_env_api_token(req, _WRONG, _mgr()) is False
    assert getattr(req.state, "api_token", False) is False
    assert effective_user(req) is None
    # Middleware maps this miss to HTTP 401 Invalid API token.
    source = Path("app.py").read_text(encoding="utf-8")
    bearer = source[source.index('# --- Bearer token auth'): source.index("# --- Cookie-based session")]
    assert "accept_env_api_token" in bearer
    assert bearer.index("accept_env_api_token") < bearer.index("_refresh_token_cache")
    assert 'status_code=401, content={"error": "Invalid API token"}' in bearer


def test_env_token_owner_is_first_admin_not_api():
    """Sandboxed current_user 'api' is never the env-token owner when an admin exists."""
    mgr = SimpleNamespace(users={
        "api": {"is_admin": False},
        "tylarcam": {"is_admin": True},
        "other": {"is_admin": True},
    })
    assert env_api_token_owner(mgr) == "tylarcam"


def test_notes_and_similar_list_routes_use_effective_user():
    """Env Bearer must scope notes/tasks/library/Jarvis to the operator, not literal 'api'."""
    notes = Path("routes/note_routes.py").read_text(encoding="utf-8")
    tasks = Path("routes/task_routes.py").read_text(encoding="utf-8")
    docs = Path("routes/document_routes.py").read_text(encoding="utf-8")
    prompts = Path("routes/prompt_routes.py").read_text(encoding="utf-8")
    memory = Path("routes/memory_routes.py").read_text(encoding="utf-8")
    skills = Path("routes/skills_routes.py").read_text(encoding="utf-8")
    assert "from src.auth_helpers import effective_user" in notes
    assert "return effective_user(request)" in notes
    assert "get_current_user(request)" not in notes
    assert "from src.auth_helpers import effective_user" in tasks
    assert "return effective_user(request)" in tasks
    assert "get_current_user(request)" not in tasks
    assert "user = get_current_user(request)" not in docs
    assert "user = effective_user(request)" in docs
    assert "from src.auth_helpers import effective_user" in prompts
    assert "return effective_user(request)" in prompts
    assert "get_current_user(request)" not in prompts
    assert "from src.auth_helpers import effective_user, require_authenticated_request" in memory
    assert "return effective_user(request)" in memory
    assert "require_authenticated_request(request)" in memory
    assert "require_user(request)" not in memory
    assert "get_current_user(request)" not in memory
    assert "from src.auth_helpers import effective_user" in skills
    assert "return effective_user(request)" in skills
    assert "get_current_user(request)" not in skills


def test_notes_list_matching_env_token_uses_operator_owner(monkeypatch):
    """GET /api/notes with a stamped env token filters as tylarcam, not 'api'."""
    import routes.note_routes as note_routes

    captured = {}

    class _Query:
        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return []

    class _Db:
        def query(self, *args, **kwargs):
            return _Query()

        def close(self):
            pass

    def _capture_owner_filter(q, model, user, include_shared=True):
        captured["user"] = user
        return q

    monkeypatch.setattr(note_routes, "SessionLocal", lambda: _Db())
    monkeypatch.setattr("src.auth_helpers.owner_filter", _capture_owner_filter)

    monkeypatch.setenv("ODYSSEUS_API_TOKEN", _ENV)
    req = _req()
    assert accept_env_api_token(req, _ENV, _mgr()) is True
    assert effective_user(req) == "tylarcam"
    assert req.state.current_user == "api"

    endpoint = next(
        route.endpoint
        for route in note_routes.setup_note_routes().routes
        if route.path == "/api/notes" and "GET" in (route.methods or set())
    )
    endpoint(req)
    assert captured["user"] == "tylarcam"


def test_jarvis_list_routes_matching_env_token_uses_operator_owner(monkeypatch):
    """GET prompts/memory/skills with a stamped env token filter as tylarcam, not 'api'."""
    import asyncio
    from unittest.mock import MagicMock

    import routes.memory_routes as memory_routes
    import routes.prompt_routes as prompt_routes
    import routes.skills_routes as skills_routes

    captured = {}

    class _Query:
        def filter(self, criterion):
            captured["prompts"] = getattr(getattr(criterion, "right", None), "value", None)
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return []

    class _Db:
        def query(self, *args, **kwargs):
            return _Query()

        def close(self):
            pass

    monkeypatch.setattr(prompt_routes, "SessionLocal", lambda: _Db())

    def _capture_load(key):
        def _load(owner=None):
            captured[key] = owner
            return []
        return _load

    mem = MagicMock()
    mem.load = _capture_load("memory")
    skills = MagicMock()
    skills.load = _capture_load("skills")

    monkeypatch.setenv("ODYSSEUS_API_TOKEN", _ENV)
    req = _req()
    assert accept_env_api_token(req, _ENV, _mgr()) is True
    assert req.state.current_user == "api"
    assert effective_user(req) == "tylarcam"

    list_prompts = next(
        route.endpoint
        for route in prompt_routes.setup_prompt_routes().routes
        if route.path == "/api/prompts" and "GET" in (route.methods or set())
    )
    list_memory = next(
        route.endpoint
        for route in memory_routes.setup_memory_routes(mem, MagicMock()).routes
        if route.path == "/api/memory" and "GET" in (route.methods or set())
    )
    list_skills = next(
        route.endpoint
        for route in skills_routes.setup_skills_routes(skills).routes
        if route.path == "/api/skills" and "GET" in (route.methods or set())
    )
    list_prompts(req)
    list_memory(req)
    asyncio.run(list_skills(req))
    assert captured["prompts"] == "tylarcam"
    assert captured["memory"] == "tylarcam"
    assert captured["skills"] == "tylarcam"


def _memory_endpoint(mem, sm, path, method="POST"):
    import routes.memory_routes as memory_routes

    return next(
        route.endpoint
        for route in memory_routes.setup_memory_routes(mem, sm).routes
        if route.path == path and method in (route.methods or set())
    )


def _probe_mem(owner="tylarcam"):
    """In-memory fixture only — never touches live memories."""
    from unittest.mock import MagicMock

    entry = {
        "id": "probe-mem-1",
        "text": "Jarvis money fact (test fixture)",
        "owner": owner,
        "pinned": False,
        "category": "fact",
    }
    mem = MagicMock()
    mem.load_all.return_value = [entry]
    return mem, entry


def _extract_endpoint(mem, sm):
    return _memory_endpoint(mem, sm, "/api/memory/extract")


def _anon_req():
    return SimpleNamespace(
        state=SimpleNamespace(current_user=None, api_token=False),
        app=SimpleNamespace(
            state=SimpleNamespace(auth_manager=SimpleNamespace(is_configured=True)),
        ),
        client=SimpleNamespace(host="203.0.113.10"),
    )


def test_extract_matching_env_token_is_not_403(monkeypatch):
    """Stamped env Bearer is the operator, so extract must not 403 as 'api'."""
    import asyncio
    from unittest.mock import MagicMock

    import pytest
    from fastapi import HTTPException

    monkeypatch.setenv("ODYSSEUS_API_TOKEN", _ENV)
    monkeypatch.setenv("AUTH_ENABLED", "true")
    req = _req()
    assert accept_env_api_token(req, _ENV, _mgr()) is True
    assert effective_user(req) == "tylarcam"

    sm = MagicMock()
    sm.get_session.side_effect = KeyError("missing")
    extract = _extract_endpoint(MagicMock(), sm)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(extract(request=req, session="no-such-session"))
    assert exc.value.status_code != 403
    assert exc.value.status_code == 404


def test_extract_rejects_anonymous_when_auth_configured(monkeypatch):
    """Extract stays closed to unauthenticated callers; Bearer is not optional."""
    import asyncio

    import pytest
    from fastapi import HTTPException
    from unittest.mock import MagicMock

    monkeypatch.setenv("AUTH_ENABLED", "true")
    extract = _extract_endpoint(MagicMock(), MagicMock())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(extract(request=_anon_req(), session="any"))
    assert exc.value.status_code == 401


def test_wrong_env_token_maps_to_401_not_extract_403():
    """A non-matching ody_ Bearer is rejected at middleware as Invalid API token."""
    source = Path("app.py").read_text(encoding="utf-8")
    bearer = source[source.index('# --- Bearer token auth'): source.index("# --- Cookie-based session")]
    assert 'status_code=401, content={"error": "Invalid API token"}' in bearer
    # Extract no longer uses require_user, which 403s the 'api' pseudo-user.
    memory = Path("routes/memory_routes.py").read_text(encoding="utf-8")
    extract_fn = memory[memory.index("@router.post(\"/extract\")"): memory.index("@router.post(\"/audit\")")]
    assert "require_authenticated_request(request)" in extract_fn
    assert "require_user(request)" not in extract_fn


def _stamped_env_req(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_API_TOKEN", _ENV)
    monkeypatch.setenv("AUTH_ENABLED", "true")
    req = _req()
    assert accept_env_api_token(req, _ENV, _mgr()) is True
    assert effective_user(req) == "tylarcam"
    assert req.state.current_user == "api"
    return req


def test_add_matching_env_token_is_not_403(monkeypatch):
    """Stamped env Bearer files as the operator, not sandbox 'api'."""
    import asyncio
    from unittest.mock import MagicMock

    from src.request_models import MemoryAddRequest

    captured = {}

    def _load(owner=None):
        captured["load_owner"] = owner
        return []

    def _add_entry(text, source, category, owner=None):
        captured["add_owner"] = owner
        return {"id": "probe-1", "text": text, "owner": owner, "source": source, "category": category}

    mem = MagicMock()
    mem.load.side_effect = _load
    mem.find_duplicates.return_value = False
    mem.add_entry.side_effect = _add_entry
    mem.load_all.return_value = []

    req = _stamped_env_req(monkeypatch)
    add = _memory_endpoint(mem, MagicMock(), "/api/memory/add")
    result = asyncio.run(add(
        request=req,
        memory_data=MemoryAddRequest(
            text="Jarvis auth probe: operator filing path (harmless)."
        ),
    ))
    assert result["ok"] is True
    assert captured["load_owner"] == "tylarcam"
    assert captured["add_owner"] == "tylarcam"


def test_add_rejects_anonymous_when_auth_configured(monkeypatch):
    import asyncio
    from unittest.mock import MagicMock

    import pytest
    from fastapi import HTTPException

    from src.request_models import MemoryAddRequest

    monkeypatch.setenv("AUTH_ENABLED", "true")
    add = _memory_endpoint(MagicMock(), MagicMock(), "/api/memory/add")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(add(
            request=_anon_req(),
            memory_data=MemoryAddRequest(text="should not file"),
        ))
    assert exc.value.status_code == 401


def test_import_matching_env_token_is_not_403(monkeypatch):
    """Stamped env Bearer reaches import after auth; 400 is not a token 403."""
    import asyncio
    from unittest.mock import MagicMock

    import pytest
    from fastapi import HTTPException

    import routes.memory_routes as memory_routes

    monkeypatch.setattr(memory_routes, "resolve_endpoint", lambda *a, **k: (None, None, {}))
    req = _stamped_env_req(monkeypatch)
    import_fn = _memory_endpoint(MagicMock(), MagicMock(), "/api/memory/import")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(import_fn(request=req, session=None, file=MagicMock()))
    assert exc.value.status_code != 403
    assert exc.value.status_code == 400


def test_import_rejects_anonymous_when_auth_configured(monkeypatch):
    import asyncio
    from unittest.mock import MagicMock

    import pytest
    from fastapi import HTTPException

    monkeypatch.setenv("AUTH_ENABLED", "true")
    import_fn = _memory_endpoint(MagicMock(), MagicMock(), "/api/memory/import")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(import_fn(request=_anon_req(), session=None, file=MagicMock()))
    assert exc.value.status_code == 401


def test_wrong_env_token_maps_to_401_not_add_import_403():
    """Wrong ody_ Bearer is middleware 401; mutate routes no longer 403 via require_user."""
    source = Path("app.py").read_text(encoding="utf-8")
    bearer = source[source.index('# --- Bearer token auth'): source.index("# --- Cookie-based session")]
    assert 'status_code=401, content={"error": "Invalid API token"}' in bearer
    memory = Path("routes/memory_routes.py").read_text(encoding="utf-8")
    helper = memory[memory.index("def _require_memory_write"): memory.index("def _assert_session_owner")]
    assert "require_authenticated_request(request)" in helper
    assert "require_user(request)" not in helper
    add_fn = memory[memory.index("@router.post(\"/add\""): memory.index("@router.get(\"\")")]
    import_fn = memory[memory.index("@router.post(\"/import\")"): memory.index("@router.post(\"/{memory_id}/pin\")")]
    pin_fn = memory[memory.index("@router.post(\"/{memory_id}/pin\")"): memory.index("@router.get(\"/{memory_id}\")")]
    update_fn = memory[memory.index("@router.put(\"/{memory_id}\")"): memory.index("@router.delete(\"/{memory_id}\")")]
    delete_fn = memory[memory.index("@router.delete(\"/{memory_id}\")"):]
    for fn in (add_fn, import_fn, pin_fn, update_fn, delete_fn):
        assert "_require_memory_write(request)" in fn
        assert "require_user(request)" not in fn
    assert "require_privilege(request, \"can_manage_memory\")" in helper


def test_pin_matching_env_token_is_not_403(monkeypatch):
    """Stamped env Bearer can pin a filed fact without privilege 403."""
    from unittest.mock import MagicMock

    mem, entry = _probe_mem()
    req = _stamped_env_req(monkeypatch)
    pin = _memory_endpoint(mem, MagicMock(), "/api/memory/{memory_id}/pin")
    result = pin(request=req, memory_id="probe-mem-1", pinned=True)
    assert result["ok"] is True
    assert result["pinned"] is True
    assert entry["pinned"] is True
    mem.save.assert_called_once()


def test_pin_rejects_anonymous_when_auth_configured(monkeypatch):
    from unittest.mock import MagicMock

    import pytest
    from fastapi import HTTPException

    monkeypatch.setenv("AUTH_ENABLED", "true")
    pin = _memory_endpoint(MagicMock(), MagicMock(), "/api/memory/{memory_id}/pin")
    with pytest.raises(HTTPException) as exc:
        pin(request=_anon_req(), memory_id="probe-mem-1", pinned=True)
    assert exc.value.status_code == 401


def test_update_matching_env_token_is_not_403(monkeypatch):
    """Stamped env Bearer can rewrite a filed fact without privilege 403."""
    from unittest.mock import MagicMock

    mem, entry = _probe_mem()
    req = _stamped_env_req(monkeypatch)
    update = _memory_endpoint(mem, MagicMock(), "/api/memory/{memory_id}", "PUT")
    result = update(
        request=req,
        memory_id="probe-mem-1",
        text="Jarvis money fact updated (test fixture)",
        category="fact",
    )
    assert result["ok"] is True
    assert entry["text"] == "Jarvis money fact updated (test fixture)"
    mem.save.assert_called_once()


def test_update_rejects_anonymous_when_auth_configured(monkeypatch):
    from unittest.mock import MagicMock

    import pytest
    from fastapi import HTTPException

    monkeypatch.setenv("AUTH_ENABLED", "true")
    update = _memory_endpoint(MagicMock(), MagicMock(), "/api/memory/{memory_id}", "PUT")
    with pytest.raises(HTTPException) as exc:
        update(request=_anon_req(), memory_id="probe-mem-1", text="should not write", category=None)
    assert exc.value.status_code == 401


def test_delete_matching_env_token_is_not_403(monkeypatch):
    """Stamped env Bearer can delete a mock fixture; never live-deletes."""
    from unittest.mock import MagicMock

    mem, _entry = _probe_mem()
    req = _stamped_env_req(monkeypatch)
    delete = _memory_endpoint(mem, MagicMock(), "/api/memory/{memory_id}", "DELETE")
    result = delete(request=req, memory_id="probe-mem-1")
    assert result["ok"] is True
    saved = mem.save.call_args[0][0]
    assert all(row.get("id") != "probe-mem-1" for row in saved)


def test_delete_rejects_anonymous_when_auth_configured(monkeypatch):
    from unittest.mock import MagicMock

    import pytest
    from fastapi import HTTPException

    monkeypatch.setenv("AUTH_ENABLED", "true")
    delete = _memory_endpoint(MagicMock(), MagicMock(), "/api/memory/{memory_id}", "DELETE")
    with pytest.raises(HTTPException) as exc:
        delete(request=_anon_req(), memory_id="probe-mem-1")
    assert exc.value.status_code == 401
