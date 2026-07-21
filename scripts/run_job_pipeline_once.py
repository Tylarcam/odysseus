#!/usr/bin/env python3
"""Run job pipeline ingest + auto_process for a single JD (CLI helper)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

JD_DEFAULT = """About the role
You'll work directly with the CEO on whatever moves the company forward. One week it's writing a proposal for a Fortune 500 prospect. The next it's running point on a client call. The next it's drafting LinkedIn content, reconciling invoices, or building a competitive analysis ahead of a pitch.

Up until now, the CEO has personally written each proposal, run every client call, and owned every operational task outside of engineering. That has worked to get us here. It is not how we will scale.

If you want a clean lane and a defined role, this is not it. If you want a front-row seat to scaling an AI native company, this is exactly it.

What we're looking for

AI is your default way of working. You use Claude or equivalent tools daily and can demonstrate evidence of this.
High agency. You move without being told, ship before it's perfect, and figure things out.
You want to do real work across strategy, sales, marketing, and operations. Not just one of them.
Based in or willing to relocate to San Francisco. This is an in-person role, minimum 3 days a week.

What this is not
This is not a Chief of Staff role focused on deck prep and board meetings. This is not a sales role. This is not a marketing role. This is the role of operating alongside the founder on whatever matters most.
"""


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run job pipeline with auto_process")
    parser.add_argument("--company", default="AI Native Startup")
    parser.add_argument("--role", default="Founders Operating Partner")
    parser.add_argument("--jd-file", type=Path, help="Path to JD markdown/text file")
    parser.add_argument("--location", default="San Francisco, CA (hybrid 3d/wk)")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--apply-url", default="")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    _load_env()

    jd_text = args.jd_file.read_text(encoding="utf-8") if args.jd_file else JD_DEFAULT

    import core.database as cdb
    from src.job_pipeline.orchestrator import inbound_job_event
    from src.job_pipeline.store import get_job_events, job_event_to_dict

    # Ensure tables exist
    cdb.Base.metadata.create_all(bind=cdb.engine)

    payload = {
        "company": args.company,
        "role": args.role,
        "jd_text": jd_text.strip(),
        "source": args.source,
        "location": args.location,
    }
    if args.apply_url:
        payload["apply_url"] = args.apply_url

    job = inbound_job_event(payload, source=args.source, auto_process=True)
    events = [job_event_to_dict(e) for e in get_job_events(job["id"])]

    out = {"job": job, "events": events}
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print("Job ID:", job.get("id"))
        print("Status:", job.get("status"))
        print("Terminal:", job.get("terminal_status"))
        print("Folder:", job.get("folder_slug"))
        print("JD path:", job.get("jd_path"))
        print("Gate score:", job.get("gate_score"))
        print("Match score:", job.get("match_score"))
        print("Handoff doc:", job.get("handoff_doc_id"))
        print("Evaluation:", job.get("evaluation_path"))
        print("\nRecent events:")
        for ev in events[-8:]:
            print(f"  {ev.get('to_status')}: {ev.get('message')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
