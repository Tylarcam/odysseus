import pytest
from fastapi import HTTPException

from routes.chat_helpers import (
    _enforce_chat_privileges,
    clean_thinking_for_save,
    needs_auto_name,
    save_assistant_response,
)


class _AuthManager:
    def __init__(self, privileges):
        self._privileges = privileges

    def get_privileges(self, username):
        assert username == "alice"
        return self._privileges


class _Request:
    def __init__(self, privileges):
        self.app = type("App", (), {})()
        self.app.state = type("State", (), {"auth_manager": _AuthManager(privileges)})()


class _Session:
    def __init__(self, model):
        self.model = model


def test_allowed_models_legacy_empty_list_remains_unrestricted(monkeypatch):
    monkeypatch.setattr("routes.chat_helpers.get_current_user", lambda request: "alice")

    _enforce_chat_privileges(
        _Request({"allowed_models": [], "max_messages_per_day": 0}),
        _Session("provider/model-a"),
    )


def test_allowed_models_explicit_empty_restricted_list_blocks_all_models(monkeypatch):
    monkeypatch.setattr("routes.chat_helpers.get_current_user", lambda request: "alice")

    with pytest.raises(HTTPException) as exc:
        _enforce_chat_privileges(
            _Request({
                "allowed_models": [],
                "allowed_models_restricted": True,
                "max_messages_per_day": 0,
            }),
            _Session("provider/model-a"),
        )

    assert exc.value.status_code == 403
    assert "provider/model-a" in exc.value.detail


def test_allowed_models_nonempty_list_still_restricts_without_new_flag(monkeypatch):
    monkeypatch.setattr("routes.chat_helpers.get_current_user", lambda request: "alice")

    _enforce_chat_privileges(
        _Request({"allowed_models": ["provider/model-a"], "max_messages_per_day": 0}),
        _Session("provider/model-a"),
    )
    with pytest.raises(HTTPException):
        _enforce_chat_privileges(
            _Request({"allowed_models": ["provider/model-a"], "max_messages_per_day": 0}),
            _Session("provider/model-b"),
        )


def test_no_restriction_allows_any_model(monkeypatch):
    monkeypatch.setattr("routes.chat_helpers.get_current_user", lambda request: "alice")

    privs = {"allowed_models": [], "block_all_models": False, "max_messages_per_day": 0}
    _enforce_chat_privileges(_Request(privs), _Session("provider/model-a"))
    _enforce_chat_privileges(_Request(privs), _Session("provider/model-z"))


def test_specific_allowlist_blocks_models_outside_it(monkeypatch):
    monkeypatch.setattr("routes.chat_helpers.get_current_user", lambda request: "alice")

    privs = {
        "allowed_models": ["gpt-4"],
        "block_all_models": False,
        "max_messages_per_day": 0,
    }
    _enforce_chat_privileges(_Request(privs), _Session("gpt-4"))
    with pytest.raises(HTTPException) as exc:
        _enforce_chat_privileges(_Request(privs), _Session("gpt-3.5"))
    assert exc.value.status_code == 403


def test_block_all_models_blocks_regardless_of_allowed_models_contents(monkeypatch):
    monkeypatch.setattr("routes.chat_helpers.get_current_user", lambda request: "alice")

    # Even if allowed_models contains entries, block_all_models wins.
    privs = {
        "allowed_models": ["gpt-4", "gpt-3.5"],
        "block_all_models": True,
        "max_messages_per_day": 0,
    }
    with pytest.raises(HTTPException) as exc:
        _enforce_chat_privileges(_Request(privs), _Session("gpt-4"))
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException):
        _enforce_chat_privileges(_Request(privs), _Session("anything-else"))


def test_admin_user_is_never_blocked(monkeypatch):
    from core.auth import ADMIN_PRIVILEGES

    monkeypatch.setattr("routes.chat_helpers.get_current_user", lambda request: "admin")

    class _AdminAuthManager:
        def get_privileges(self, username):
            assert username == "admin"
            return dict(ADMIN_PRIVILEGES)

    class _AdminRequest:
        def __init__(self):
            self.app = type("App", (), {})()
            self.app.state = type("State", (), {"auth_manager": _AdminAuthManager()})()

    _enforce_chat_privileges(_AdminRequest(), _Session("provider/model-a"))
    _enforce_chat_privileges(_AdminRequest(), _Session("anything-else"))


class _FakeSession:
    def __init__(self, model="selected-model"):
        self.model = model
        self.history = []

    def add_message(self, message):
        self.history.append(message)


@pytest.mark.parametrize("name,expected", [
    # 24h format (the bug this PR fixes)
    ("deepseek-v4-flash 14:05:33", True),
    ("qwq 17:46:02", True),
    ("gemma3 23:59:59", True),
    ("claude-sonnet 4 0:00:00", True),

    # 12h format (was already working)
    ("deepseek-v4-flash 2:05:33 PM", True),
    ("qwq 06:46:02 AM", True),
    ("claude-sonnet-4 8:05:17 am", True),

    # empty / default
    ("", True),
    ("  ", False),
    ("Chat: something", True),

    # custom titles – should NOT trigger auto-naming
    ("custom title", False),
    ("CW Decoder for STM32", False),
    ("my chat about python", False),
    ("Fix the login bug", False),
])
def test_needs_auto_name(name, expected):
    assert needs_auto_name(name) == expected, f"needs_auto_name({name!r}) should be {expected}"


@pytest.mark.parametrize("raw,expected", [
    ("Fix the STM32 CW decoder", "Fix the STM32 CW decoder"),
    ('  "Grant proposal recap"  ', "Grant proposal recap"),
    ("<think>noise</think>Rename sidebar chats", "Rename sidebar chats"),
    ("", ""),
    ("Chat: leftover", ""),
    ("x" * 81, ""),
    ("A short title.", "A short title"),
])
def test_sanitize_generated_title(raw, expected):
    from routes.chat_helpers import sanitize_generated_title
    assert sanitize_generated_title(raw) == expected


def test_parse_session_rename_map_matches_id_prefix():
    from routes.chat_helpers import parse_session_rename_map
    sessions = [
        {"id": "abc12345-ffff", "name": "Chat: leftover"},
        {"id": "def67890-aaaa", "name": "Chat: other"},
    ]
    raw = '{"names": {"abc12345": "STM32 decoder", "def67890": "Grant recap"}}'
    assert parse_session_rename_map(raw, sessions) == {
        "abc12345-ffff": "STM32 decoder",
        "def67890-aaaa": "Grant recap",
    }


def test_build_rename_prompt_includes_recap_and_id_prefix():
    from routes.chat_helpers import build_rename_prompt
    prompt = build_rename_prompt([
        {
            "id": "abc12345-ffff",
            "name": "Chat: leftover",
            "recap": "User: fix the decoder | Assistant: here is the patch",
        }
    ])
    assert "abc12345" in prompt
    assert "fix the decoder" in prompt
    assert '{"names":' in prompt


def test_clean_thinking_for_save_extracts_gemma4_thought_channel():
    content, metadata = clean_thinking_for_save(
        "<|channel>thought\ninternal reasoning<channel|>Final answer.",
        {"model": "google/gemma-4-31B-it"},
    )

    assert content == "Final answer."
    assert metadata["thinking"] == "internal reasoning"
    assert metadata["model"] == "google/gemma-4-31B-it"


def test_clean_thinking_for_save_strips_empty_gemma4_thought_channel():
    content, metadata = clean_thinking_for_save(
        "<|channel>thought\n<channel|>Final answer.",
        {"model": "google/gemma-4-31B-it"},
    )

    assert content == "Final answer."
    assert "thinking" not in metadata


def test_clean_thinking_for_save_unwraps_gemma4_response_channel():
    content, metadata = clean_thinking_for_save(
        "<|channel>thought\ninternal reasoning<channel|><|channel>response\nFinal answer.<channel|>",
        {"model": "google/gemma-4-31B-it"},
    )

    assert content == "Final answer."
    assert metadata["thinking"] == "internal reasoning"


def test_clean_thinking_for_save_extracts_thought_tag():
    content, metadata = clean_thinking_for_save(
        "<thought>internal reasoning</thought>Final answer.",
        {},
    )

    assert content == "Final answer."
    assert metadata["thinking"] == "internal reasoning"


def test_save_assistant_response_preserves_actual_and_requested_model():
    sess = _FakeSession("selected-model")

    save_assistant_response(
        sess,
        session_manager=None,
        session_id="s1",
        full_response="hello",
        last_metrics={"model": "actual-model", "input_tokens": 1, "output_tokens": 2},
        incognito=True,
    )

    assert sess.history[-1].metadata["requested_model"] == "selected-model"
    assert sess.history[-1].metadata["model"] == "actual-model"
