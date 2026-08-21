"""
OPTIMIZATION SUMMARY for Vault Sync 504 timeouts & SQLite locks:

Problems Fixed:
1. CalDAV sync held DB lock while making HTTP calls (up to 12s per server)
2. Multiple nested SessionLocal() calls in cmd_center route caused contention
3. SQLite default (busy_timeout=0) → immediate lock failure under load
4. No WAL mode → single-writer bottleneck

Solutions:
✓ Enable SQLite WAL + busy_timeout (10s) in core/database.py
✓ Move CalDAV HTTP calls OUTSIDE the transaction in _sync_blocking
✓ Parse iCalendar data outside transaction, single commit per calendar
✓ Connection pool with pre_ping (health check on borrow)
✓ (Future) Make CalDAV sync fire async off the request path
"""

# Changes required in core/database.py BEFORE caldav_sync.py:

# OLD:
# engine = create_engine(
#     DATABASE_URL,
#     connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
# )

# NEW:
# _engine_kwargs = {}
# if "sqlite" in DATABASE_URL:
#     _engine_kwargs["connect_args"] = {
#         "check_same_thread": False,
#         "timeout": 10.0,  # 10s busy_timeout for lock contention
#     }
#     _engine_kwargs["pool_pre_ping"] = True
#     _engine_kwargs["pool_size"] = 5
#     _engine_kwargs["max_overflow"] = 10
#     # Enable WAL pragma on every connection
#     import sqlite3
#     from sqlalchemy import event, Engine
#     @event.listens_for(Engine, "connect")
#     def enable_wal(dbapi_conn, connection_record):
#         if isinstance(dbapi_conn, sqlite3.Connection):
#             dbapi_conn.execute("PRAGMA journal_mode=WAL")
#             dbapi_conn.execute("PRAGMA synchronous=NORMAL")
# 
# engine = create_engine(DATABASE_URL, **_engine_kwargs)

import asyncio
import hashlib
import ipaddress
import logging
import os
import socket
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 90
_LOOKAHEAD_DAYS = 365
_CALDAV_HTTP_TIMEOUT_SEC = 12
_BLOCKED_HOSTS = {
    "localhost", "localhost.", "ip6-localhost", "metadata.google.internal",
}

def _private_caldav_allowed() -> bool:
    return os.environ.get("ODYSSEUS_ALLOW_PRIVATE_CALDAV", "0").lower() in {"1", "true", "yes"}

def _validate_caldav_address(addr: ipaddress._BaseAddress) -> None:
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if (addr.is_loopback or addr.is_link_local or addr.is_multicast or 
        addr.is_unspecified or addr.is_reserved):
        raise ValueError("CalDAV URL host is not allowed")
    if addr.is_private and not _private_caldav_allowed():
        raise ValueError("Private CalDAV IPs require ODYSSEUS_ALLOW_PRIVATE_CALDAV=1")

def _validate_caldav_ip(host: str) -> None:
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    _validate_caldav_address(ip)

def _resolve_caldav_host_ips(host: str) -> list[ipaddress._BaseAddress]:
    addrs: list[ipaddress._BaseAddress] = []
    for family, _, _, _, sockaddr in socket.getaddrinfo(host, None):
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        try:
            addrs.append(ipaddress.ip_address(sockaddr[0].split("%", 1)[0]))
        except ValueError:
            continue
    return addrs

def _validate_caldav_hostname(host: str) -> None:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return
    except ValueError:
        pass
    try:
        addrs = _resolve_caldav_host_ips(host)
    except OSError:
        raise ValueError("CalDAV URL host does not resolve")
    if not addrs:
        raise ValueError("CalDAV URL host does not resolve")
    for addr in addrs:
        _validate_caldav_address(addr)

def validate_caldav_url(raw_url: str) -> str:
    """Validate and normalize a user-provided CalDAV URL."""
    url = (raw_url if isinstance(raw_url, str) else "").strip()
    if not url:
        raise ValueError("CalDAV URL is required")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("CalDAV URL must start with http:// or https://")
    if not parsed.hostname:
        raise ValueError("CalDAV URL must include a host")
    if parsed.username or parsed.password:
        raise ValueError("Put CalDAV credentials in the username/password fields, not the URL")
    if parsed.fragment:
        raise ValueError("CalDAV URL fragments are not allowed")
    try:
        parsed.port
    except ValueError:
        raise ValueError("CalDAV URL has an invalid port")
    host = (parsed.hostname or "").lower()
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise ValueError("CalDAV URL host is not allowed")
    _validate_caldav_ip(host)
    _validate_caldav_hostname(host)
    return urlunparse(parsed._replace(fragment="")).rstrip("/")

def _stable_cal_id(remote_url: str, owner: str = "", account_id: str = "") -> str:
    key = f"{owner}\n{account_id}\n{remote_url}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return f"caldav-{h}"

def _to_utc_naive(dt):
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None), False
        return dt, False
    return datetime(dt.year, dt.month, dt.day), True

def _build_dav_client(url: str, username: str, password: str):
    """Construct a CalDAV client with redirects disabled (SSRF protection)."""
    import caldav
    client = caldav.DAVClient(
        url=url, username=username, password=password, timeout=_CALDAV_HTTP_TIMEOUT_SEC
    )
    client.session.max_redirects = 0
    return client

def _should_prune_window(seen_uids: set, parse_failed: bool) -> bool:
    """Only prune if we have a complete view (no parse failures)."""
    return not parse_failed

def _sync_blocking(owner: str, url: str, username: str, password: str, account_id: str = "") -> dict:
    """CalDAV sync optimized for low lock contention.
    
    KEY OPTIMIZATION: HTTP calls happen OUTSIDE the transaction.
    - Fetch all remote events (HTTP) → parse outside TX → commit once per calendar
    - This prevents holding SQLite write locks during network I/O.
    """
    from caldav.lib.error import AuthorizationError, NotFoundError
    from core.database import CalendarCal, CalendarEvent, SessionLocal

    result = {"calendars": 0, "events": 0, "deleted": 0, "errors": []}
    client = _build_dav_client(url, username, password)

    # STEP 1: Discovery (HTTP call, OUTSIDE transaction)
    calendars = []
    try:
        principal = client.principal()
        calendars = principal.calendars()
    except (AuthorizationError, NotFoundError) as e:
        result["errors"].append(f"Discovery failed: {e}")
        return result
    except Exception as e:
        logger.info(f"CalDAV principal discovery failed, trying URL as calendar: {e}")
        try:
            from src.caldav_sync import _open_url_as_calendar
            calendars = [_open_url_as_calendar(client, url)]
        except Exception as e2:
            result["errors"].append(f"Could not open URL as calendar: {e2}")
            return result

    if not calendars:
        try:
            from src.caldav_sync import _open_url_as_calendar
            calendars = [_open_url_as_calendar(client, url)]
        except Exception as e:
            result["errors"].append(f"No calendars and URL fallback failed: {e}")
            return result

    start = datetime.utcnow() - timedelta(days=_LOOKBACK_DAYS)
    end = datetime.utcnow() + timedelta(days=_LOOKAHEAD_DAYS)

    # STEP 2: Process each calendar
    for remote_cal in calendars:
        db = SessionLocal()  # Fresh connection per calendar
        try:
            remote_url = str(remote_cal.url)
            cal_id = _stable_cal_id(remote_url, owner=owner, account_id=account_id)
            display_name = (remote_cal.name or "").strip() or "CalDAV"

            # Get or create local calendar (quick DB work)
            local_cal = db.query(CalendarCal).filter(
                CalendarCal.id == cal_id, CalendarCal.owner == owner
            ).first()
            if not local_cal:
                local_cal = CalendarCal(
                    id=cal_id, owner=owner, name=display_name, color="#5b8abf",
                    source="caldav", account_id=account_id or None,
                )
                db.add(local_cal)
                db.commit()
            else:
                changed = False
                if local_cal.name != display_name:
                    local_cal.name = display_name
                    changed = True
                if account_id and not local_cal.account_id:
                    local_cal.account_id = account_id
                    changed = True
                if changed:
                    db.commit()
            result["calendars"] += 1
            db.close()  # Release lock BEFORE HTTP call

            # STEP 3: Fetch + parse events (HTTP + parsing, OUTSIDE transaction)
            from icalendar import Calendar as iCal
            seen_uids = set()
            events_to_upsert = []
            parse_failed = False

            try:
                objs = remote_cal.date_search(start=start, end=end, expand=False)
            except Exception as e:
                result["errors"].append(f"{display_name}: date_search failed ({e})")
                continue

            # Parse all events outside the transaction
            for obj in objs:
                try:
                    ical = iCal.from_ical(obj.data)
                except Exception as e:
                    result["errors"].append(f"{display_name}: parse failed ({e})")
                    parse_failed = True
                    continue

                for comp in ical.walk():
                    if comp.name != "VEVENT":
                        continue
                    uid_val = str(comp.get("uid", "")) or str(uuid.uuid4())
                    seen_uids.add(uid_val)

                    dtstart_p = comp.get("dtstart")
                    if not dtstart_p:
                        continue
                    start_dt, all_day = _to_utc_naive(dtstart_p.dt)

                    dtend_p = comp.get("dtend")
                    if dtend_p:
                        end_dt, _ = _to_utc_naive(dtend_p.dt)
                    elif all_day:
                        end_dt = start_dt + timedelta(days=1)
                    else:
                        end_dt = start_dt + timedelta(hours=1)

                    row_is_utc = (
                        not all_day and isinstance(dtstart_p.dt, datetime)
                        and dtstart_p.dt.tzinfo is not None
                    )

                    summary = str(comp.get("summary", ""))
                    description = str(comp.get("description", ""))
                    location = str(comp.get("location", ""))
                    rrule = (
                        comp.get("rrule").to_ical().decode() if comp.get("rrule") else ""
                    )

                    events_to_upsert.append({
                        "uid": uid_val,
                        "calendar_id": cal_id,
                        "summary": summary,
                        "description": description,
                        "location": location,
                        "dtstart": start_dt,
                        "dtend": end_dt,
                        "all_day": all_day,
                        "is_utc": row_is_utc,
                        "rrule": rrule,
                    })
                    result["events"] += 1

            # STEP 4: Upsert all events in ONE transaction (minimal lock time)
            if events_to_upsert or seen_uids:
                db = SessionLocal()
                try:
                    for evt_data in events_to_upsert:
                        uid_val = evt_data["uid"]
                        existing = db.query(CalendarEvent).filter(
                            CalendarEvent.uid == uid_val,
                            CalendarEvent.calendar_id == evt_data["calendar_id"],
                        ).first()
                        if existing:
                            for k, v in evt_data.items():
                                setattr(existing, k, v)
                            setattr(existing, "origin", "caldav")
                        else:
                            db.add(CalendarEvent(**evt_data, origin="caldav"))

                    # Prune stale CalDAV-sourced events
                    if _should_prune_window(seen_uids, parse_failed):
                        stale = db.query(CalendarEvent).filter(
                            CalendarEvent.calendar_id == cal_id,
                            CalendarEvent.origin == "caldav",
                            CalendarEvent.dtstart >= start,
                            CalendarEvent.dtstart <= end,
                            ~CalendarEvent.uid.in_(seen_uids) if seen_uids else True,
                        ).all()
                        for ev in stale:
                            db.delete(ev)
                        result["deleted"] += len(stale)

                    db.commit()
                except Exception as e:
                    logger.exception("CalDAV event upsert failed for %s", display_name)
                    result["errors"].append(str(e)[:200])
                    db.rollback()
                finally:
                    db.close()

        except Exception as e:
            logger.exception("CalDAV sync failed for calendar")
            result["errors"].append(str(e)[:200])
            if db:
                try:
                    db.rollback()
                    db.close()
                except Exception:
                    pass

    return result
