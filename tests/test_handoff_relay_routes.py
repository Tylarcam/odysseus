"""Auth owner resolution for handoff relay API."""

from types import SimpleNamespace

from src.auth_helpers import effective_user


def test_effective_user_for_bearer_token_owner():
    req = SimpleNamespace(state=SimpleNamespace(
        current_user="api",
        api_token=True,
        api_token_owner="tylarcam",
    ))
    assert effective_user(req) == "tylarcam"


def test_effective_user_for_browser_session():
    req = SimpleNamespace(state=SimpleNamespace(current_user="tylarcam"))
    assert effective_user(req) == "tylarcam"
