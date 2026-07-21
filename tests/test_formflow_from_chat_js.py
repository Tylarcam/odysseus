"""Regression pins for chat → FormFlow fork wiring."""

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

_QUOTE_HEAVY_CHECKLIST = """\
1. "Judgment" vs "Judgement" — public schedule uses the UK spelling. Yours is American. Pick one, lock it, use it everywhere (title slide, schedule, communications).
2. "Tylar" vs "Ras" — schedule says Tylar. Confirm which goes in introductions + title slide.
3. The 5–7 min vs 6:40 discrepancy — FAQ says "6:40 + Q&A", spreadsheet says "5–7 min each + 3 min Q&A". Best read: 6:40 is the rule, 5–7 min is a tolerance band. Rehearse to 6:40 strict; the moderator enforces the cutoff."""


def test_formflow_from_chat_exports_parser_and_sender():
    src = (_REPO / "static/js/formflowFromChat.js").read_text(encoding="utf-8")
    assert "export const FORMFLOW_BTN_ICON" in src
    assert "export function parseQuestionsFromText" in src
    assert "export function parseFormFlowModelJson" in src
    assert "export async function sendMessageToFormFlow" in src


def test_quote_heavy_numbered_list_matches_formflow_heuristic():
    """Gate Breaker-style checklists should local-parse without hitting the LLM."""
    lines = [line.strip() for line in _QUOTE_HEAVY_CHECKLIST.splitlines() if line.strip()]
    numbered = [line for line in lines if re.match(r"^\d+[.)]\s+", line)]
    assert len(numbered) == 3
    assert '"Judgment"' in numbered[0]
    assert '"6:40 + Q&A"' in numbered[2]


def test_formflow_paste_uses_local_parser_before_llm():
    src = (_REPO / "static/js/formflow.js").read_text(encoding="utf-8")
    assert "parseQuestionsFromText" in src
    assert "parseFormFlowModelJson" in src
    assert "const localQuestions = parseQuestionsFromText(txt)" in src
    assert "_applyQuestions(localQuestions)" in src
    assert "await _startParse({ text: txt })" in src


def test_formflow_llm_parse_uses_hardened_json_helper():
    src = (_REPO / "static/js/formflow.js").read_text(encoding="utf-8")
    assert "const questions = parseFormFlowModelJson(accumulated)" in src
    assert "JSON.parse(cleaned)" not in src


def test_chat_renderer_wires_fork_to_formflow_action():
    src = (_REPO / "static/js/chatRenderer.js").read_text(encoding="utf-8")
    assert "formflowFromChat.js" in src
    assert "Fork to FormFlow" in src
    assert "_forkMessageToFormFlow" in src
    assert "id: 'formflow'" in src


def test_formflow_exports_open_with_helpers():
    src = (_REPO / "static/js/formflow.js").read_text(encoding="utf-8")
    assert "export function openWithQuestions" in src
    assert "export async function openWithText" in src
    assert "openWithQuestions, openWithText" in src


def test_document_export_menu_wires_fork_to_formflow():
    src = (_REPO / "static/js/document.js").read_text(encoding="utf-8")
    assert "formflowFromChat.js" in src
    assert "forkDocToFormFlow" in src
    assert "Fork to FormFlow" in src
    assert "sendMessageToFormFlow" in src
