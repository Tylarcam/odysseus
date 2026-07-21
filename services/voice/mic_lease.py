"""Cross-process microphone lease — coordinates Clicky and Odysseus web voice.

Both apps capture from the default Windows mic. Only one holder may claim at
a time. State is persisted under DATA_DIR/mic_lease.json so the Clicky worker
adapter and Odysseus app (separate processes) share the same lock file.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional

from core.atomic_io import atomic_write_json
from src.constants import DATA_DIR

LEASE_FILE = os.path.join(DATA_DIR, "mic_lease.json")
DEFAULT_TTL_SEC = 90
REALTIME_TTL_SEC = 600

_process_lock = threading.Lock()

HOLDERS = frozenset({"clicky", "odysseus"})


def _now() -> float:
    return time.time()


def _read_lease_unlocked() -> Optional[Dict[str, Any]]:
    if not os.path.isfile(LEASE_FILE):
        return None
    try:
        with open(LEASE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    expires_at = float(data.get("expires_at") or 0)
    if expires_at and _now() > expires_at:
        try:
            os.remove(LEASE_FILE)
        except OSError:
            pass
        return None
    return data


def get_status() -> Dict[str, Any]:
    with _process_lock:
        lease = _read_lease_unlocked()
    if not lease:
        return {"available": True, "holder": None, "mode": None}
    return {
        "available": False,
        "holder": lease.get("holder"),
        "mode": lease.get("mode"),
        "since": lease.get("since"),
        "expires_at": lease.get("expires_at"),
    }


def claim(
    holder: str,
    *,
    mode: str = "",
    ttl_sec: int = DEFAULT_TTL_SEC,
) -> Dict[str, Any]:
    if holder not in HOLDERS:
        return {"ok": False, "reason": "invalid_holder", "holder": holder}

    with _process_lock:
        current = _read_lease_unlocked()
        if current and current.get("holder") != holder:
            return {
                "ok": False,
                "reason": "busy",
                "holder": current.get("holder"),
                "mode": current.get("mode"),
            }

        token = str(uuid.uuid4())
        now = _now()
        lease = {
            "holder": holder,
            "token": token,
            "mode": mode or None,
            "since": now,
            "expires_at": now + max(5, int(ttl_sec)),
        }
        atomic_write_json(LEASE_FILE, lease)
        return {"ok": True, "token": token, "holder": holder, "mode": mode or None}


def release(holder: str, token: Optional[str] = None) -> Dict[str, Any]:
    with _process_lock:
        current = _read_lease_unlocked()
        if not current:
            return {"ok": True, "released": False}
        if current.get("holder") != holder:
            return {"ok": False, "reason": "not_owner", "holder": current.get("holder")}
        if token and current.get("token") != token:
            return {"ok": False, "reason": "token_mismatch"}
        try:
            os.remove(LEASE_FILE)
        except OSError:
            pass
        return {"ok": True, "released": True}


def refresh(holder: str, token: str, *, ttl_sec: int = DEFAULT_TTL_SEC) -> Dict[str, Any]:
    with _process_lock:
        current = _read_lease_unlocked()
        if not current:
            return {"ok": False, "reason": "no_lease"}
        if current.get("holder") != holder or current.get("token") != token:
            return {"ok": False, "reason": "not_owner", "holder": current.get("holder")}
        now = _now()
        current["expires_at"] = now + max(5, int(ttl_sec))
        current["since"] = current.get("since") or now
        atomic_write_json(LEASE_FILE, current)
        return {"ok": True, "expires_at": current["expires_at"]}
