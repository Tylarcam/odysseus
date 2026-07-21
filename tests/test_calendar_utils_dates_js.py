import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node binary not on PATH")


def _node_eval(source: str, env: dict | None = None):
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    result = subprocess.run(
        ["node", "--input-type=module", "-e", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=run_env,
    )
    return json.loads(result.stdout)


def test_calendar_date_helpers_ignore_non_string_inputs():
    values = _node_eval(
        """
        import { _addDays, _shiftDT, _localDateOf } from './static/js/calendar/utils.js';
        console.log(JSON.stringify({
          addNull: _addDays(null, 1),
          addObject: _addDays({bad: true}, 1),
          shiftNull: _shiftDT(null, 1),
          shiftObject: _shiftDT({bad: true}, 1),
          localNull: _localDateOf(null),
          localNumber: _localDateOf(123)
        }));
        """
    )

    assert values == {
        "addNull": "",
        "addObject": "",
        "shiftNull": "",
        "shiftObject": "",
        "localNull": "",
        "localNumber": "",
    }


def test_calendar_date_helpers_keep_valid_strings():
    values = _node_eval(
        """
        import { _addDays, _shiftDT, _localDateOf } from './static/js/calendar/utils.js';
        console.log(JSON.stringify({
          add: _addDays('2026-06-01', 2),
          shift: _shiftDT('2026-06-01T10:30:00', 1),
          local: _localDateOf('2026-06-01T23:30:00Z')
        }));
        """
    )

    assert values["add"] == "2026-06-03"
    assert values["shift"] == "2026-06-02T10:30:00"
    assert isinstance(values["local"], str)
    assert len(values["local"]) == 10


def test_local_parts_converts_z_to_local_wall_clock():
    """Regression: week grid must not place UTC Z hours on the local axis.

    16:00Z is 10:00 in America/Denver (MST/MDT). Label already showed local
    via Date; positioning used raw T(HH) digits and put the block at 4 PM.
    """
    values = _node_eval(
        """
        import { _localParts, _localMinutes, _localTimeHHMM } from './static/js/calendar/utils.js';
        const iso = '2026-07-21T16:00:00Z';
        const p = _localParts(iso);
        const d = new Date(iso);
        console.log(JSON.stringify({
          p,
          mins: _localMinutes(iso),
          hhmm: _localTimeHHMM(iso),
          expectedHours: d.getHours(),
          expectedMins: d.getMinutes(),
          expectedDate: [
            d.getFullYear(),
            String(d.getMonth() + 1).padStart(2, '0'),
            String(d.getDate()).padStart(2, '0'),
          ].join('-'),
          utcHourFromRegex: parseInt(iso.match(/T(\\d{2})/)[1], 10),
          offsetMinutes: new Date().getTimezoneOffset(),
        }));
        """,
        env={"TZ": "America/Denver"},
    )

    assert values["p"]["hours"] == values["expectedHours"]
    assert values["p"]["minutes"] == values["expectedMins"]
    assert values["p"]["date"] == values["expectedDate"]
    assert values["mins"] == values["expectedHours"] * 60 + values["expectedMins"]
    assert values["hhmm"] == (
        f"{values['expectedHours']:02d}:{values['expectedMins']:02d}"
    )
    # When the host is not on UTC, local hours must differ from Z digits —
    # that's the exact class of bug in the screenshot.
    if values["offsetMinutes"] != 0:
        assert values["p"]["hours"] != values["utcHourFromRegex"]


def test_local_parts_keeps_naive_wall_clock():
    values = _node_eval(
        """
        import { _localParts, _localTimeHHMM } from './static/js/calendar/utils.js';
        console.log(JSON.stringify({
          p: _localParts('2026-07-21T10:00:00'),
          hhmm: _localTimeHHMM('2026-07-21T10:00:00'),
          offsetAware: _localTimeHHMM('2026-07-21T10:00:00-06:00'),
        }));
        """
    )
    assert values["p"] == {
        "date": "2026-07-21",
        "hours": 10,
        "minutes": 0,
        "seconds": 0,
    }
    assert values["hhmm"] == "10:00"
    # Offset-aware must still produce a valid HH:MM.
    assert len(values["offsetAware"]) == 5


def test_shift_dt_aware_reemits_local_offset():
    values = _node_eval(
        """
        import { _shiftDT, _tzOffset, _localParts } from './static/js/calendar/utils.js';
        const src = '2026-07-21T16:00:00Z';
        const shifted = _shiftDT(src, 1);
        const p0 = _localParts(src);
        const p1 = _localParts(shifted);
        console.log(JSON.stringify({
          shifted,
          tz: _tzOffset(),
          hours0: p0.hours,
          hours1: p1.hours,
          date0: p0.date,
          date1: p1.date,
        }));
        """
    )
    assert values["shifted"].endswith(values["tz"])
    assert values["hours0"] == values["hours1"]
    # Date advanced by one calendar day in local terms.
    assert values["date1"] > values["date0"]
