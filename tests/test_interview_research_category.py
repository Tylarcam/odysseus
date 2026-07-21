"""Interview category + published interview-research skill."""

from pathlib import Path

from src.deep_research import CATEGORY_PROMPTS


def test_interview_category_prompt_exists():
    assert "interview" in CATEGORY_PROMPTS
    text = CATEGORY_PROMPTS["interview"]
    assert "Coach briefing" in text
    assert "STAR" in text
    assert "Interviewer dossiers" in text


def test_interview_research_skill_published():
    skill = Path(__file__).resolve().parents[1] / "data" / "skills" / "general" / "interview-research" / "SKILL.md"
    assert skill.is_file()
    body = skill.read_text(encoding="utf-8")
    assert "interview-research" in body
    assert "research-swarm" in body
