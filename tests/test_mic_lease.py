"""Tests for cross-process microphone lease coordination."""

from __future__ import annotations

import json
import time

import pytest

from services.voice import mic_lease


@pytest.fixture(autouse=True)
def isolated_lease_file(tmp_path, monkeypatch):
    lease_path = tmp_path / "mic_lease.json"
    monkeypatch.setattr(mic_lease, "LEASE_FILE", str(lease_path))
    yield lease_path


def test_claim_and_release():
    claimed = mic_lease.claim("odysseus", mode="recorder")
    assert claimed["ok"] is True
    assert claimed["token"]

    status = mic_lease.get_status()
    assert status["available"] is False
    assert status["holder"] == "odysseus"

    released = mic_lease.release("odysseus", claimed["token"])
    assert released["ok"] is True
    assert released["released"] is True
    assert mic_lease.get_status()["available"] is True


def test_clicky_blocks_odysseus():
    clicky = mic_lease.claim("clicky", mode="ptt")
    assert clicky["ok"] is True

    odysseus = mic_lease.claim("odysseus", mode="recorder")
    assert odysseus["ok"] is False
    assert odysseus["reason"] == "busy"
    assert odysseus["holder"] == "clicky"


def test_same_holder_can_reclaim():
    first = mic_lease.claim("odysseus", mode="recorder")
    second = mic_lease.claim("odysseus", mode="realtime")
    assert second["ok"] is True
    assert second["token"] != first["token"]


def test_stale_lease_expires(isolated_lease_file):
    isolated_lease_file.write_text(
        json.dumps(
            {
                "holder": "clicky",
                "token": "old",
                "mode": "ptt",
                "since": time.time() - 200,
                "expires_at": time.time() - 1,
            }
        ),
        encoding="utf-8",
    )
    status = mic_lease.get_status()
    assert status["available"] is True
