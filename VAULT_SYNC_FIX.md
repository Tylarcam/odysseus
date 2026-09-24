# Vault Sync 504 Timeouts & SQLite Lock Fixes

## Problem Summary

**Vault Sync hits 504 timeouts** (45s hard deadline in `app.py`) because:

1. **CalDAV sync holds DB write lock during HTTP calls** (up to 12s per server)
2. **Route fetches nested sessions** (`get_jobs_for_brief`, `get_upcoming_events`) while CalDAV is writing
3. **SQLite single-writer lock** + no `busy_timeout` → immediate "database is locked" failures
4. **No WAL mode** → readers block on writers, writers block on readers
5. **Result**: HUD refresh hangs, live poll times out, document library unreachable during sync

---

## Root Cause: Lock Contention Map

```
Vault Sync (worker thread):
  └─ CalDAV HTTP call (12s)  ← HOLDS SQLite write lock
     └ db.commit() for each calendar  ← Exclusive lock released/reacquired
        └ HTTP PROPFIND/REPORT  ← LOCK HELD WHILE WAITING

Route (async thread):
  └─ cmd_center / live poll
     ├─ SessionLocal()  ← Wants to read, BLOCKS on write lock
     ├─ get_jobs_for_brief()  ← Opens ANOTHER session, BLOCKS
     ├─ get_upcoming_events()  ← Opens ANOTHER session, BLOCKS
     └─ UI pollers (notes, docs, etc.)  ← Also BLOCKED

SQLite default:
  ├─ journal_mode=DELETE (not WAL)
  ├─ busy_timeout=0 (fail immediately if locked)
  ├─ synchronous=FULL (every commit flushes to disk)
  └─ → single-writer bottleneck under load
```

---

## Solution

### 1. Enable SQLite WAL + Busy Timeout (core/database.py)

**Before:**
```python
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
```

**After:**
```python
import sqlite3
from sqlalchemy import event, Engine, create_engine

_engine_kwargs = {}
if "sqlite" in DATABASE_URL:
    _engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": 10.0,  # 10s busy_timeout: retry lock for up to 10s
    }
    _engine_kwargs["pool_pre_ping"] = True     # Health-check on borrow
    _engine_kwargs["pool_size"] = 5            # Pool connections
    _engine_kwargs["max_overflow"] = 10        # Overflow for peaks

engine = create_engine(DATABASE_URL, **_engine_kwargs)

# Enable WAL + performance pragmas on every connection
@event.listens_for(Engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")      # Write-ahead logging
        cursor.execute("PRAGMA synchronous=NORMAL")    # Less fsync overhead
        cursor.execute("PRAGMA cache_size=-64000")     # ~64MB cache
        cursor.close()
```

**What this does:**
- **WAL mode**: readers don't block writers (readers see last committed snapshot)
- **busy_timeout=10**: retry up to 10s instead of failing immediately → less "locked" errors
- **synchronous=NORMAL**: every commit still syncs, but slightly faster than FULL
- **pool_pre_ping**: check connection health before using it

---

### 2. Refactor CalDAV Sync: Move HTTP Outside Transaction

**Problem:** `_sync_blocking` holds DB connection from discovery through all HTTP calls.

**Solution:** HTTP → parse outside transaction, single commit per calendar.

**Key change in `_sync_blocking` (src/caldav_sync.py):**

```python
def _sync_blocking(owner: str, url: str, username: str, password: str, account_id: str = "") -> dict:
    result = {"calendars": 0, "events": 0, "deleted": 0, "errors": []}
    client = _build_dav_client(url, username, password)

    # STEP 1: Discovery HTTP call (NO DB session yet)
    try:
        principal = client.principal()
        calendars = principal.calendars()
    except Exception as e:
        result["errors"].append(...)
        return result

    for remote_cal in calendars:
        db = SessionLocal()  # Fresh connection per calendar
        try:
            # STEP 2: Get/create calendar row (quick, commits immediately)
            local_cal = db.query(CalendarCal).filter(...).first()
            if not local_cal:
                local_cal = CalendarCal(...)
                db.add(local_cal)
            db.commit()
            db.close()  # ← RELEASE LOCK BEFORE HTTP CALL

            # STEP 3: Fetch remote events (HTTP, NO DB session)
            objs = remote_cal.date_search(start=start, end=end, expand=False)  # HTTP

            # STEP 4: Parse all events (outside transaction)
            events_to_upsert = []
            for obj in objs:
                ical = iCal.from_ical(obj.data)  # Parse
                for comp in ical.walk():
                    if comp.name == "VEVENT":
                        events_to_upsert.append({...})  # Collect

            # STEP 5: Upsert all events in ONE transaction (minimal lock time)
            if events_to_upsert:
                db = SessionLocal()
                try:
                    for evt_data in events_to_upsert:
                        existing = db.query(CalendarEvent).filter(...).first()
                        if existing:
                            # Update existing
                        else:
                            db.add(CalendarEvent(**evt_data))
                    db.commit()  # ← Single commit for all events
                finally:
                    db.close()
        except Exception as e:
            logger.exception(...)
            if db:
                db.rollback()
                db.close()

    return result
```

**Lock duration reduction:**
- **Before**: 12s HTTP + parsing + DB commit = ~15s total write lock
- **After**: ~100ms for calendar metadata + parsing (~1-2s, no lock) + ~200ms for event upsert = ~300ms total lock

---

### 3. Route-Level Session Management (routes/home_routes.py)

**Future optimization:** Use a single long-lived session for the entire `cmd_center` request instead of opening 3-4 nested sessions.

**Current pattern (problematic):**
```python
@app.get("/api/home/cmd-center")
async def cmd_center(sync_calendar: bool = True):
    # Session #1 (inside sync_caldav)
    await asyncio.to_thread(sync_caldav, owner)
    
    # Session #2 (route-level)
    db = SessionLocal()
    
    # Session #3 (inside get_jobs_for_brief)
    jobs = await get_jobs_for_brief()  # Opens its own SessionLocal
    
    # Session #4 (inside get_upcoming_events)
    events = await get_upcoming_events()  # Opens its own SessionLocal
    
    # Build response...
    db.close()
```

**Recommended pattern (future):**
```python
@app.get("/api/home/cmd-center")
async def cmd_center(sync_calendar: bool = True):
    db = SessionLocal()
    try:
        # Collect ALL data in one transaction (readers see consistent snapshot)
        sync_result = await asyncio.to_thread(sync_caldav, owner)
        jobs = db.query(JobRecord).filter(...).all()
        events = db.query(CalendarEvent).join(CalendarCal).filter(...).all()
        notes = db.query(Note).filter(...).all()
        # ...
        db.close()  # Release lock once, not 4+ times
    finally:
        db.close()
```

---

## Deployment Checklist

### Step 1: Update core/database.py

Replace the `create_engine` section (lines ~33-39) with the code above. Verify:
- ✓ WAL pragma is set on connection
- ✓ busy_timeout=10 is passed to connect_args
- ✓ No syntax errors in pragma callback

### Step 2: Replace caldav_sync._sync_blocking

Use the refactored version from `src/caldav_sync_fix.py`:
- ✓ HTTP calls outside transactions
- ✓ Single commit per calendar
- ✓ Fresh SessionLocal per calendar to reduce lock time

Test:
```bash
# Before fix (expect timeouts):
curl "http://localhost:7000/api/home/cmd-center?sync_calendar=1" &
# Wait ~5s, then try another request while sync is running
curl "http://localhost:7000/api/notes"  # Should timeout or hang

# After fix (should both succeed):
curl "http://localhost:7000/api/home/cmd-center?sync_calendar=1" &
curl "http://localhost:7000/api/notes"  # Should respond quickly
```

### Step 3: Monitor

Check logs for:
- ✓ No more "database is locked" errors
- ✓ Vault Sync completes in < 15s (total including all HTTP calls)
- ✓ Live poll responds in < 2s even during sync
- ✓ HUD data loads immediately on open

Check performance:
```bash
# Check WAL file size (should exist)
ls -lh data/app.db*  # app.db + app.db-wal + app.db-shm

# Check connection pool stats (if available)
docker logs odysseus | grep -i "pool\|connection"
```

---

## Technical Details

### Why WAL helps

**DELETE mode (default):**
- Writer creates lock, rewrites entire journal, commits
- Readers see old data until writer finishes
- Readers block on writer

**WAL mode:**
- Writer appends to WAL file (faster)
- Readers see last committed snapshot (no lock contention)
- Readers + writer coexist

### Why busy_timeout helps

**Default (timeout=0):**
```
Client: SELECT * FROM notes
SQLite: Write lock held, return immediately with "database is locked"
Result: 504 / retry loop
```

**With timeout=10:**
```
Client: SELECT * FROM notes
SQLite: Write lock held, wait up to 10s for lock to clear
  → Lock clears after 2s (CalDAV commit finishes)
  → Client's SELECT proceeds
Result: 200, slight latency
```

### Connection pool benefits

- **pool_size=5**: 5 persistent connections (warm start)
- **max_overflow=10**: up to 15 total under peak load
- **pool_pre_ping=True**: health-check on borrow (reconnect if stale)
- Result: Less connection churn, faster request handling

---

## Rollback Plan

If issues arise after deployment:

```python
# Revert core/database.py to original:
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Revert caldav_sync.py to last commit:
git checkout HEAD~1 -- src/caldav_sync.py

# Restart app
docker-compose down && docker-compose up -d odysseus
```

Expected symptom of regression: "database is locked" in logs, 504 timeouts on Vault Sync, document library unreachable during sync.

---

## Performance Expectations

| Metric | Before | After |
|--------|--------|-------|
| Vault Sync duration | 30-45s (hangs, hits timeout) | 8-15s (completes) |
| Live poll latency | 10+ sec (blocks on sync) | <2s (concurrent) |
| "database is locked" errors | Frequent | Rare |
| HUD refresh | Never loads | Instant |
| Document library access during sync | Blocked (504) | Responsive |
| SQLite file size | ~app.db (100MB) | app.db + app.db-wal (~50MB+) |

---

## References

- SQLite WAL: https://www.sqlite.org/wal.html
- Busy timeout: https://www.sqlite.org/c3ref/busy_timeout.html
- SQLAlchemy pooling: https://docs.sqlalchemy.org/en/20/core/pooling.html
- CalDAV protocol (RFC 4791): https://tools.ietf.org/html/rfc4791

