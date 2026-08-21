"""Shared auth helpers used by all route files."""

import os
import secrets
from typing import Optional
from fastapi import Request, HTTPException, WebSocket

# Operator machine token from ODYSSEUS_API_TOKEN. Broad enough for agents to
# compile the CEO brief and fetch notes/docs; excludes email:send.
ENV_API_TOKEN_ID = "env"
ENV_API_TOKEN_SCOPES = [
    "chat",
    "todos:read",
    "todos:write",
    "documents:read",
    "documents:write",
    "email:read",
    "email:draft",
    "calendar:read",
    "calendar:write",
    "memory:read",
    "memory:write",
    "cookbook:read",
    "cookbook:launch",
]


def match_env_api_token(raw_token: str, env_token: Optional[str] = None) -> bool:
    """True when the Bearer equals ``ODYSSEUS_API_TOKEN`` (no SQLite)."""
    offered = (raw_token or "").strip()
    expected = (env_token if env_token is not None else os.getenv("ODYSSEUS_API_TOKEN") or "").strip()
    if not offered.startswith("ody_") or not expected.startswith("ody_"):
        return False
    if len(offered) < 12 or len(expected) < 12:
        return False
    if len(offered) != len(expected):
        return False
    return secrets.compare_digest(offered, expected)


def env_api_token_owner(auth_manager) -> Optional[str]:
    """First admin (else first configured user) for the env operator token."""
    users = getattr(auth_manager, "users", None) or {}
    if not isinstance(users, dict) or not users:
        return None
    for name, data in users.items():
        if isinstance(data, dict) and data.get("is_admin"):
            return name
    return next(iter(users), None)


def stamp_env_api_token(request, owner: str) -> None:
    """Attribute an env-token Bearer as the sandboxed owner, same as SQLite hits."""
    request.state.current_user = "api"
    request.state.api_token = True
    request.state.api_token_id = ENV_API_TOKEN_ID
    request.state.api_token_owner = owner
    request.state.api_token_scopes = list(ENV_API_TOKEN_SCOPES)


def accept_env_api_token(
    request,
    raw_token: str,
    auth_manager,
    env_token: Optional[str] = None,
) -> bool:
    """Stamp owner on ``request`` when Bearer matches the env token. No DB I/O."""
    if not match_env_api_token(raw_token, env_token=env_token):
        return False
    owner = env_api_token_owner(auth_manager)
    if not owner:
        return False
    stamp_env_api_token(request, owner)
    return True


def get_current_user(request: Request) -> Optional[str]:
    """Get current username from request state (set by auth middleware)."""
    return getattr(request.state, 'current_user', None)


def effective_user(request: Request) -> Optional[str]:
    """The real human behind the request, for ownership/attribution.

    Cookie sessions resolve to the logged-in username. Bearer ``ody_`` callers
    come through as the sandboxed pseudo-user "api" so they can't wander into
    cookie/user routes by default, but their token was minted by, and belongs
    to, a real owner stamped on ``request.state.api_token_owner``. Routes that
    should attribute a token's actions to that owner (sessions, chat history)
    call this instead of :func:`get_current_user`, so a paired client sees and
    creates the SAME data as the owner's desktop UI rather than a separate
    "api"-owned silo.

    For cookie sessions this is identical to :func:`get_current_user`, so
    swapping a route over is a no-op for browser users. A bearer token with no
    owner falls back to :func:`get_current_user` (the "api" pseudo-user), so it
    never escalates.
    """
    if getattr(request.state, "api_token", False):
        owner = getattr(request.state, "api_token_owner", None)
        if owner:
            return owner
    return get_current_user(request)


def _is_api_token_request(request: Request) -> bool:
    """Return True when middleware authenticated a bearer API token."""
    return bool(getattr(request.state, "api_token", False))


def require_authenticated_request(request: Request) -> str:
    """Allow either a browser session or a valid bearer API token.

    This is intentionally narrower than :func:`require_user`: use it only for
    routes that need authentication but do not read or mutate owner-scoped
    user data. Owner-scoped routes should use ``require_user`` for browser
    sessions or their own API-token scope/owner gate.
    """
    if _is_api_token_request(request):
        return effective_user(request) or ""
    return require_user(request)


def _auth_disabled() -> bool:
    """True when the operator has explicitly turned off auth via .env.
    Mirrors the AUTH_ENABLED parse in app.py / core/middleware.py so the
    three call sites agree on what "off" means."""
    return os.getenv("AUTH_ENABLED", "true").lower() == "false"


def require_user(request: Request) -> str:
    """FastAPI dependency: reject unauthenticated callers when the upstream
    auth middleware was bypassed unexpectedly (e.g. SSRF from a sibling
    service). Returns the resolved username, or "" in single-user / anonymous
    modes where no username is available.

    The three "" cases are:
      1. AUTH_ENABLED=false — the operator explicitly turned auth off.
         The full /login flow is skipped (issue #622), so route-level
         require_user must let the request through too instead of 401-ing
         and forcing the browser to /login.
      2. Unconfigured first-run + loopback caller — pre-setup access from
         localhost so the operator can hit the SPA before creating the
         first admin.
      3. LOCALHOST_BYPASS=true + loopback caller — documented dev bypass.

    Use this on routes that touch user data so middleware misconfig can't
    open them up.
    """
    if _is_api_token_request(request):
        raise HTTPException(403, "API tokens must use a scope-aware API route")

    u = get_current_user(request)
    if u:
        return u
    # Operator-disabled auth: honor it at the route layer too. Without this,
    # routes that depend on require_user 401, the front-end fetch wrapper
    # redirects to /login, and the user sees a login page despite
    # AUTH_ENABLED=false (issue #622). Docker / reverse-proxy deployments
    # hit this because requests arrive from a non-loopback client.host, so
    # the loopback fall-through below never fires.
    if _auth_disabled():
        return ""
    auth_mgr = getattr(request.app.state, "auth_manager", None)
    client = getattr(request, "client", None)
    host = (client.host if client else "") or ""
    is_loopback = host in ("127.0.0.1", "::1", "localhost")
    # LOCALHOST_BYPASS=true is the dev-only "I'm on loopback, skip auth"
    # switch. Mirror the middleware so routes don't 401 the same caller
    # the middleware just let through.
    if is_loopback and os.getenv("LOCALHOST_BYPASS", "false").lower() == "true":
        return ""
    if auth_mgr is not None and getattr(auth_mgr, "is_configured", False):
        raise HTTPException(401, "Not authenticated")
    # Unconfigured / first-run mode: only allow loopback callers.
    if is_loopback:
        return ""
    raise HTTPException(401, "Not authenticated")


def require_privilege(request: Request, key: str) -> str:
    """Reject callers whose `auth.json` privilege flag for `key` is False.
    Returns the username so the route handler can keep using it.

    Admins always have every privilege via `auth_manager.get_privileges`
    (which returns ADMIN_PRIVILEGES wholesale), so this is a no-op for
    them. In unauthenticated single-user mode (`require_user` returns ""),
    privileges aren't enforced.
    """
    user = require_user(request)
    if not user:
        return user
    auth_mgr = getattr(request.app.state, "auth_manager", None)
    if auth_mgr is None:
        return user
    try:
        privs = auth_mgr.get_privileges(user) or {}
    except Exception:
        return user
    if not isinstance(privs, dict):
        privs = {}
    # True = permitted; missing key defaults to permitted (unknown privileges
    # fail open — the UI gates display-side).
    if not privs.get(key, True):
        raise HTTPException(403, f"Your account is not allowed to {key.replace('_', ' ')}.")
    return user


def authenticate_websocket(websocket: WebSocket) -> Optional[str]:
    """WebSocket counterpart to require_authenticated_request.

    Starlette's ``BaseHTTPMiddleware`` (AuthMiddleware in app.py) never runs
    for WebSocket connections, so ``websocket.state.current_user`` is never
    populated the way it is for HTTP requests — each WS route must check auth
    itself. Mirrors the cookie/bearer-token checks in app.py's AuthMiddleware
    but returns None instead of redirecting/raising HTTPException, since the
    caller must close the socket with a WS close code, not an HTTP response.

    Returns the resolved username ("" in single-user / anonymous / auth-off
    modes), or None if the connection should be rejected.
    """
    auth_manager = getattr(websocket.app.state, "auth_manager", None)
    if auth_manager is None:
        # Auth disabled entirely (AUTH_ENABLED=false at startup — no
        # auth_manager was attached to app.state at all).
        return ""

    if _auth_disabled():
        return ""

    # Bearer token (API clients) — same "ody_" scheme as HTTP.
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.startswith("Bearer ody_"):
        raw_token = auth_header[7:]
        if len(raw_token) < 12 or len(raw_token) > 100:
            return None
        env_owner = env_api_token_owner(auth_manager) if match_env_api_token(raw_token) else None
        if env_owner:
            return env_owner
        try:
            from core.database import ApiToken, SessionLocal
            import bcrypt

            db = SessionLocal()
            try:
                prefix = raw_token[:8]
                candidates = (
                    db.query(ApiToken)
                    .filter(ApiToken.token_prefix == prefix, ApiToken.is_active == True)  # noqa: E712
                    .all()
                )
                for tok in candidates:
                    if bcrypt.checkpw(raw_token.encode(), tok.token_hash.encode()):
                        return tok.owner or ""
            finally:
                db.close()
        except Exception:
            return None
        return None

    # Cookie-based session — same cookie name as routes/auth_routes.py.
    from routes.auth_routes import SESSION_COOKIE

    token = websocket.cookies.get(SESSION_COOKIE)
    if auth_manager.validate_token(token):
        return auth_manager.get_username_for_token(token) or ""

    if not getattr(auth_manager, "is_configured", False):
        client = websocket.client
        host = (client.host if client else "") or ""
        if host in ("127.0.0.1", "::1", "localhost"):
            return ""

    return None


def owner_filter(query, model_cls, user: str, *, include_shared: bool = True):
    """Filter `query` so only rows owned by `user` (and optionally null-owner
    'shared' rows) come through. No-op when `user` is empty (single-user
    mode). Returns the modified query."""
    if not user:
        return query
    if include_shared:
        return query.filter((model_cls.owner == user) | (model_cls.owner == None))  # noqa: E711
    return query.filter(model_cls.owner == user)
