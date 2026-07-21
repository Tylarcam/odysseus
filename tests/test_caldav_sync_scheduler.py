"""Background CalDAV sync loop — owner discovery and interval parsing."""

from src.task_scheduler import TaskScheduler


def _sched():
    return TaskScheduler(session_manager=object())


def test_caldav_sync_interval_sec_defaults(monkeypatch):
    monkeypatch.delenv("ODYSSEUS_CALDAV_SYNC_INTERVAL_SEC", raising=False)
    assert _sched()._caldav_sync_interval_sec() == 900


def test_caldav_sync_interval_sec_respects_env(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_CALDAV_SYNC_INTERVAL_SEC", "300")
    assert _sched()._caldav_sync_interval_sec() == 300


def test_caldav_sync_interval_sec_floors_at_sixty(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_CALDAV_SYNC_INTERVAL_SEC", "10")
    assert _sched()._caldav_sync_interval_sec() == 60


def test_caldav_sync_owners_includes_caldav_configured_users(monkeypatch):
    sched = _sched()

    def fake_load():
        return {
            "_users": {
                "alice": {"caldav_accounts": []},
                "bob": {
                    "caldav_accounts": [
                        {"id": "1", "url": "https://dav.example.com", "username": "u", "password": "p"}
                    ]
                },
            }
        }

    monkeypatch.setattr("routes.prefs_routes._load", fake_load)
    owners = sched._caldav_sync_owners()
    assert owners == ["bob"]
