"""Regression pins for FormFlow decision flows + handoff completion screen."""

from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def test_formflow_wires_flows_handoffs_and_completion_screen():
    src = (_REPO / "static/js/formflow.js").read_text(encoding="utf-8")
    assert "from './formflowFlows.js'" in src
    assert "from './formflowHandoffs.js'" in src
    assert "from './handoff.js'" in src
    assert "openWithFlow" in src
    assert "ff-screen-handoff" in src
    assert "Continue to handoffs" in src
    assert "buildHandoffOptions" in src
    assert "createHandoffDocument" in src
    assert "visibleQuestions" in src


def test_formflow_flows_exports_gate_breaker():
    src = (_REPO / "static/js/formflowFlows.js").read_text(encoding="utf-8")
    assert "GATE_BREAKER_FLOW" in src
    assert "gate-breaker" in src
    assert "questionVisible" in src
    assert "visibleQuestions" in src


def test_formflow_handoffs_generates_human_and_delegate():
    src = (_REPO / "static/js/formflowHandoffs.js").read_text(encoding="utf-8")
    assert "buildGateBreakerHandoffs" in src
    assert "buildHandoffOptions" in src
    assert "target: 'human'" in src
    assert "target: 'cursor'" in src
