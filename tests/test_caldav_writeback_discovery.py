"""Write-back calendar discovery must mirror pull-path Google URL mapping."""

import sys
import types

import pytest

from src.caldav_writeback import _discover_calendars

_GOOGLE_PRINCIPAL = "https://apidata.googleusercontent.com/caldav/v2/me@gmail.com/user"
_GOOGLE_EVENTS = "https://apidata.googleusercontent.com/caldav/v2/me@gmail.com/events"


@pytest.fixture(autouse=True)
def _fake_caldav_lib(monkeypatch):
    err = types.ModuleType("caldav.lib.error")
    err.AuthorizationError = type("AuthorizationError", (Exception,), {})
    err.NotFoundError = type("NotFoundError", (Exception,), {})
    lib = types.ModuleType("caldav.lib")
    lib.error = err
    fake = types.ModuleType("caldav")
    fake.lib = lib
    monkeypatch.setitem(sys.modules, "caldav", fake)
    monkeypatch.setitem(sys.modules, "caldav.lib", lib)
    monkeypatch.setitem(sys.modules, "caldav.lib.error", err)


class _FakeCalendar:
    def __init__(self, url):
        self.url = url


class _FakePrincipal:
    def calendars(self):
        return []


class _FakeClient:
    def __init__(self, url):
        self.url = url
        self.opened = []

    def principal(self):
        return _FakePrincipal()

    def calendar(self, url):
        self.opened.append(url)
        return _FakeCalendar(url)


def test_discover_calendars_maps_google_principal_to_events_collection():
    client = _FakeClient(_GOOGLE_PRINCIPAL)
    cals = _discover_calendars(client, account_url=_GOOGLE_PRINCIPAL)
    assert len(cals) == 1
    assert str(cals[0].url).rstrip("/").endswith("/events")
    assert _GOOGLE_EVENTS in client.opened[0]


def test_discover_calendars_uses_principal_calendars_when_present():
    class _PrincipalWithCals:
        def calendars(self):
            return [_FakeCalendar("https://example.com/cal/home/")]

    client = _FakeClient("https://example.com/")
    client.principal = lambda: _PrincipalWithCals()
    cals = _discover_calendars(client, account_url="https://example.com/")
    assert len(cals) == 1
    assert "example.com" in str(cals[0].url)
