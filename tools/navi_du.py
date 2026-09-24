#!/usr/bin/env python
r"""navi-du: NaviCust/PET-styled disk storage visualizer (HTML renderer).

Scans real folders on this Windows machine, builds a byte-weighted
hierarchy, and writes a self-contained HTML report that renders it as a
MegaMan Battle Network "Memory Map" using the ConnectGlobe hash-dither
technique (offscreen occupancy mask -> 6px hash-dithered cells).

For a terminal-native version (chunky flat-colored blocks, no browser),
see navi_du_tui.py instead.

Usage:
    python tools/navi_du.py            # scan default roots, open in browser
    python tools/navi_du.py --quick    # scan only AppData\Local + code/ (fast iteration)
    python tools/navi_du.py --no-open  # write the HTML but don't launch a browser

Re-run any time to rescan and get a fresh report.
"""
from __future__ import annotations

import argparse
import json
import os
import webbrowser

from navi_du_scan import scan

HTML_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "navi_du_template.html")


def build_html(data: dict) -> str:
    with open(HTML_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()
    safe_json = json.dumps(data).replace("</", "<\\/")
    return template.replace("__NAVI_DU_DATA__", safe_json)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="scan only AppData\\Local + code\\ (fast)")
    ap.add_argument("--no-open", action="store_true", help="write the report but don't launch a browser")
    ap.add_argument("--out", default=None, help="output HTML path (default: %%TEMP%%\\navi-du\\report.html)")
    args = ap.parse_args()

    def on_root_done(r):
        from navi_du_scan import human
        print(f"  scanned {r['name']:<22} {human(r['bytes']):>10}  ({r['errors']} access errors)")

    print(f"navi-du: scanning {'(quick) ' if args.quick else ''}real folders on this machine...")
    data = scan(args.quick, on_root_done=on_root_done)
    print(f"navi-du: scan complete in {data['scan_seconds']}s"
          f"{', ' + str(data['error_count']) + ' access-denied paths skipped' if data['had_errors'] else ''}")

    out_path = args.out or os.path.join(os.environ.get("TEMP", "."), "navi-du", "report.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    html = build_html(data)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"navi-du: wrote {out_path}")

    if not args.no_open:
        webbrowser.open("file:///" + out_path.replace("\\", "/"))


if __name__ == "__main__":
    main()
