"""Regression: PUT /api/email/accounts/{id} must persist is_default changes."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from core.database import EmailAccount
import routes.email_routes as email_routes


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _session_factory(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'email_accounts.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(email_routes, "SessionLocal", factory)
    return factory


def _seed_accounts(factory, owner="alice"):
    now = _utcnow()
    db = factory()
    try:
        db.add_all(
            [
                EmailAccount(
                    id="acct-a",
                    owner=owner,
                    name="Primary",
                    is_default=True,
                    enabled=True,
                    imap_user="a@example.com",
                    from_address="a@example.com",
                    created_at=now,
                    updated_at=now,
                ),
                EmailAccount(
                    id="acct-b",
                    owner=owner,
                    name="Secondary",
                    is_default=False,
                    enabled=True,
                    imap_user="b@example.com",
                    from_address="b@example.com",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def _route_endpoint(router, path: str, method: str):
    method = method.upper()
    for route in router.routes:
        if route.path == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"route not found: {method} {path}")


@pytest.mark.asyncio
async def test_update_email_account_swaps_default(monkeypatch, tmp_path):
    factory = _session_factory(tmp_path, monkeypatch)
    _seed_accounts(factory)

    monkeypatch.setattr(email_routes, "_assert_owns_account", lambda _id, _owner: None)

    router = email_routes.setup_email_routes()
    update = _route_endpoint(router, "/api/email/accounts/{account_id}", "PUT")

    result = await update("acct-b", {"is_default": True}, owner="alice")
    assert result["ok"] is True

    db = factory()
    try:
        rows = {
            row.id: bool(row.is_default)
            for row in db.query(EmailAccount).order_by(EmailAccount.id).all()
        }
    finally:
        db.close()

    assert rows == {"acct-a": False, "acct-b": True}
