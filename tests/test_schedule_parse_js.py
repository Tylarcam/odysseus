"""Regression: scheduleParse.js — time-only defaults to today, embedded times work."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node binary not on PATH")

# Fixed "now": Wed 2026-06-17 15:00 local (parser uses local Date)
_NOW_ISO = "2026-06-17T15:00:00"


def _parse_cases(cases):
    source = f"""
        import {{ parseScheduleFromLine, toLocalIso }} from './static/js/scheduleParse.js';
        const now = new Date('{_NOW_ISO}');
        const cases = {json.dumps(cases)};
        const out = cases.map((c) => {{
          const r = parseScheduleFromLine(c.line, now);
          return {{
            line: c.line,
            title: r.title,
            start: toLocalIso(r.start),
            hasExplicitDate: r.hasExplicitDate,
          }};
        }});
        console.log(JSON.stringify(out));
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_time_only_defaults_to_today():
    rows = _parse_cases([
        {"line": "Submit proposal at 2pm"},
        {"line": "2pm standup"},
        {"line": "Grab loops at 10am"},
    ])
    assert rows[0]["start"] == "2026-06-17T14:00:00"
    assert rows[0]["title"] == "Submit proposal"
    assert rows[1]["start"] == "2026-06-17T14:00:00"
    assert rows[1]["title"] == "standup"
    assert rows[2]["start"] == "2026-06-17T10:00:00"


def test_explicit_date_with_time():
    rows = _parse_cases([
        {"line": "tomorrow 3pm Review"},
        {"line": "Monday at 9am sync"},
        {"line": "2026-06-20 15:00 Planning session"},
    ])
    assert rows[0]["start"] == "2026-06-18T15:00:00"
    assert rows[0]["title"] == "Review"
    assert rows[1]["start"] == "2026-06-22T09:00:00"
    assert rows[1]["title"] == "sync"
    assert rows[2]["start"] == "2026-06-20T15:00:00"


def test_no_time_defaults_today_nine_am_not_tomorrow():
    rows = _parse_cases([{"line": "Just a task with no time"}])
    assert rows[0]["start"] == "2026-06-17T09:00:00"
    assert rows[0]["hasExplicitDate"] is False


def test_relative_in_minutes():
    rows = _parse_cases([{"line": "in 30m Call client"}])
    assert rows[0]["start"] == "2026-06-17T15:30:00"
    assert rows[0]["title"] == "Call client"
