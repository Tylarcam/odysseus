"""Runs the Node directive-triage peek suite (tests/test_cmd_center_directive.mjs)."""

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_HAS_NODE = shutil.which("node") is not None


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_cmd_center_directive_suite():
    result = subprocess.run(
        ["node", "--test", str(_REPO / "tests" / "test_cmd_center_directive.mjs")],
        cwd=_REPO,
        capture_output=True,
        timeout=30,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"node --test failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
