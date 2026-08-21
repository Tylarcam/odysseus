import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routes.prefs_routes as prefs_routes


def test_load_ignores_non_object_prefs_file(tmp_path, monkeypatch):
    prefs_file = tmp_path / "user_prefs.json"
    prefs_file.write_text(json.dumps(["not", "a", "prefs", "object"]), encoding="utf-8")
    monkeypatch.setattr(prefs_routes, "PREFS_FILE", str(prefs_file))

    assert prefs_routes._load() == {}
    assert prefs_routes._load_for_user("alice") == {}


def test_load_keeps_object_prefs_file(tmp_path, monkeypatch):
    prefs_file = tmp_path / "user_prefs.json"
    prefs_file.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    monkeypatch.setattr(prefs_routes, "PREFS_FILE", str(prefs_file))

    assert prefs_routes._load_for_user("alice") == {"theme": "dark"}


def test_normalize_writing_dictionary_words_shapes_and_bounds():
    assert prefs_routes.normalize_writing_dictionary_words(None) == []
    assert prefs_routes.normalize_writing_dictionary_words(
        ["Odysseus", "  odysseus ", "Ithaca", 12, ""]
    ) == ["Odysseus", "Ithaca"]
    assert prefs_routes.normalize_writing_dictionary_words(
        {"version": 1, "words": ["Alpha", "alpha", "Beta"]}
    ) == ["Alpha", "Beta"]

    long_word = "x" * (prefs_routes.MAX_WRITING_DICTIONARY_WORD_LEN + 10)
    capped = prefs_routes.normalize_writing_dictionary_words([long_word])
    assert capped == ["x" * prefs_routes.MAX_WRITING_DICTIONARY_WORD_LEN]

    overflow = [f"w{i}" for i in range(prefs_routes.MAX_WRITING_DICTIONARY_WORDS + 25)]
    bounded = prefs_routes.normalize_writing_dictionary_words(overflow)
    assert len(bounded) == prefs_routes.MAX_WRITING_DICTIONARY_WORDS
    assert bounded[0] == "w0"
    assert bounded[-1] == f"w{prefs_routes.MAX_WRITING_DICTIONARY_WORDS - 1}"

    with pytest.raises(HTTPException) as exc:
        prefs_routes.normalize_writing_dictionary_words("nope")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        prefs_routes.normalize_writing_dictionary_words({"version": 1})
    assert exc.value.status_code == 400


def _prefs_client(tmp_path, monkeypatch):
    prefs_file = tmp_path / "user_prefs.json"
    monkeypatch.setattr(prefs_routes, "PREFS_FILE", str(prefs_file))
    monkeypatch.setattr(prefs_routes, "get_current_user", lambda request: "alice")
    app = FastAPI()
    app.include_router(prefs_routes.setup_prefs_routes())
    return TestClient(app), prefs_file


def test_put_writing_dictionary_words_normalizes_and_clears(tmp_path, monkeypatch):
    client, prefs_file = _prefs_client(tmp_path, monkeypatch)

    res = client.put(
        "/api/prefs/writing_dictionary_words",
        json={"value": ["Odysseus", "odysseus", "Ithaca"]},
    )
    assert res.status_code == 200
    assert res.json() == {
        "key": "writing_dictionary_words",
        "value": ["Odysseus", "Ithaca"],
    }

    stored = json.loads(prefs_file.read_text(encoding="utf-8"))
    assert stored["_users"]["alice"]["writing_dictionary_words"] == ["Odysseus", "Ithaca"]

    # Phase-1 object shape accepted on PUT
    res = client.put(
        "/api/prefs/writing_dictionary_words",
        json={"value": {"version": 1, "words": ["Hermes"]}},
    )
    assert res.status_code == 200
    assert res.json()["value"] == ["Hermes"]

    # Clear / delete via PUT null → []
    res = client.put("/api/prefs/writing_dictionary_words", json={"value": None})
    assert res.status_code == 200
    assert res.json()["value"] == []

    res = client.put("/api/prefs/writing_dictionary_words", json={"value": {"oops": True}})
    assert res.status_code == 400


def test_put_other_prefs_keys_still_unbounded(tmp_path, monkeypatch):
    client, _ = _prefs_client(tmp_path, monkeypatch)
    res = client.put("/api/prefs/theme", json={"value": {"name": "dark", "colors": {}}})
    assert res.status_code == 200
    assert res.json()["value"] == {"name": "dark", "colors": {}}
