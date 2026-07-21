#!/usr/bin/env python3
"""Live, self-driving demo of the Agentic Operator capabilities.

Run it yourself:
    cd C:\\Users\\tylar\\code\\odysseus
    .\\venv\\Scripts\\Activate.ps1          # if not already in the venv
    python scripts/operator_demo.py

What it does:
  1. Prints the operator health snapshot (works with zero sidecars running).
  2. If a Chrome/Edge DevTools endpoint is reachable (browser started with
     --remote-debugging-port=9222), walks browser_act end-to-end in a throwaway
     tab: tabs -> consent gate -> navigate -> read title -> snapshot -> audit.

Nothing here touches your existing tabs; the walkthrough opens and closes its
own demo tab. Safe to re-run.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

# Make the repo importable no matter where you run this from.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.operator.browser import browser_act
from services.operator.cdp import CdpSession
from services.operator.core import cdp_url, get_operator_status, reset_consents

SID = "operator-demo"


def hr(title):
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def show(label, result):
    print(f"\n--- {label} ---")
    print(json.dumps(result, indent=2, default=str)[:1500])


# ── 1. Health snapshot (no sidecars required) ──────────────────────────────
hr("1. OPERATOR STATUS  (each capability + whether its sidecar is up)")
status = get_operator_status(force=True)
for name, entry in status["capabilities"].items():
    mark = "UP  " if entry.get("available") else "down"
    hint = "" if entry.get("available") else f"   -> {entry.get('hint', '')}"
    print(f"  [{mark}] {name:<18} {entry.get('endpoint', '')}{hint}")


# ── 2. Browser walkthrough (only if a CDP endpoint is reachable) ───────────
def browser_ws():
    with urllib.request.urlopen(f"{cdp_url()}/json/version", timeout=3) as r:
        return json.loads(r.read().decode())["webSocketDebuggerUrl"]


def cdp_reachable():
    try:
        browser_ws()
        return True
    except Exception:
        return False


if not cdp_reachable():
    hr("2. BROWSER WALKTHROUGH — SKIPPED")
    print("No Chrome/Edge DevTools endpoint on", cdp_url())
    print("Start one (close the browser first), then re-run:")
    print('  & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222')
    print("  (or the same for msedge.exe)")
    sys.exit(0)

hr("2. BROWSER_ACT WALKTHROUGH  (live, against your running browser)")
reset_consents()

show("browser_act tabs (read-only, no consent)", browser_act({"action": "tabs"}, session_id=SID))

with CdpSession(browser_ws(), timeout=5) as s:
    demo = s.command("Target.createTarget", {"url": "about:blank"})["targetId"]
print(f"\n[opened throwaway demo tab {demo} — your other tabs untouched]")

show("navigate WITHOUT approval  (consent gate blocks it)",
     browser_act({"action": "navigate", "url": "https://example.com", "target_id": demo}, session_id=SID))

show("navigate WITH user_approved=true  (executes)",
     browser_act({"action": "navigate", "url": "https://example.com",
                  "user_approved": True, "target_id": demo}, session_id=SID))

time.sleep(1.5)
show("evaluate document.title  (confirms it landed)",
     browser_act({"action": "evaluate", "expression": "document.title", "target_id": demo}, session_id=SID))

show("snapshot  (interactive elements with stable refs)",
     browser_act({"action": "snapshot", "target_id": demo}, session_id=SID))

try:
    with CdpSession(browser_ws(), timeout=5) as s:
        s.command("Target.closeTarget", {"targetId": demo})
    print("\n[closed demo tab]")
except Exception as e:
    print(f"\n[could not close demo tab: {e}]")

# ── 3. Audit trail this run wrote ──────────────────────────────────────────
hr("3. OPERATOR_AUDIT  (mutations + denials from this run; reads are not logged)")
from core.database import OperatorAudit, SessionLocal

db = SessionLocal()
try:
    rows = (db.query(OperatorAudit)
            .filter(OperatorAudit.session_id == SID)
            .order_by(OperatorAudit.timestamp).all())
    for r in rows:
        print(f"  {r.timestamp:%H:%M:%S} | {r.capability} | {r.action:<9} | "
              f"result={r.result:<7} | target={r.target}")
    if not rows:
        print("  (none)")
finally:
    db.close()

print("\nDone. Re-run anytime; it always uses a fresh demo tab.\n")
