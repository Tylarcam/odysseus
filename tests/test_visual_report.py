from bs4 import BeautifulSoup
import json
import re

from src.visual_report import generate_visual_report, _build_export_markdown


def test_visual_report_toc_links_match_rendered_heading_ids():
    report = """
# Automated Crypto Trading Bot Strategies

### **1.0 Introduction & Research Scope**

Intro body.

### **2.0 Determining the "Best" Configuration**

Configuration body.
"""

    html = generate_visual_report(
        "crypto bot strategies",
        report,
        sources=[],
        stats={},
        session_id="rp-test",
    )
    soup = BeautifulSoup(html, "html.parser")

    links = soup.select(".toc-sidebar nav a")
    assert [link.get_text(strip=True) for link in links] == [
        "1.0 Introduction & Research Scope",
        '2.0 Determining the "Best" Configuration',
    ]

    for link in links:
        target_id = link["href"].removeprefix("#")
        target = soup.find(id=target_id)
        assert target is not None
        assert target.name in {"h2", "h3"}


def test_visual_report_export_markdown_button_and_payload():
    report = """## Key Findings

Some insight here.
"""
    sources = [{"url": "https://example.com/a", "title": "Example A"}]
    stats = {"Duration": "2m", "URLs": 3}

    html = generate_visual_report(
        "What is the best approach?",
        report,
        sources=sources,
        stats=stats,
        session_id="rp-export",
    )
    soup = BeautifulSoup(html, "html.parser")

    assert soup.find("button", id="btn-md") is not None
    assert "Download Markdown" in html

    match = re.search(r"var exportMarkdown = (.+?);\n", html)
    assert match is not None
    export_md = json.loads(match.group(1))

    assert export_md.startswith("# ")
    assert "> **Research question:** What is the best approach?" in export_md
    assert "Duration: 2m" in export_md
    assert "URLs: 3" in export_md
    assert "## Key Findings" in export_md
    assert "Some insight here." in export_md
    assert "## Sources" in export_md
    assert "[Example A](https://example.com/a)" in export_md


def test_build_export_markdown_includes_metadata_and_sources():
    md = _build_export_markdown(
        question="test question",
        title="Report Title",
        report_markdown="## Section\n\nBody text.",
        sources=[{"url": "https://x.test", "title": "X"}],
        stats={"Model": "gpt-test"},
        timestamp="July 7, 2026 at 20:00",
    )
    assert md.startswith("# Report Title")
    assert "test question" in md
    assert "Model: gpt-test" in md
    assert "[X](https://x.test)" in md


def test_visual_report_listen_modal_transport_controls():
    html = generate_visual_report(
        "interview brief",
        "## Findings\n\nBody.",
        sources=[],
        stats={},
        session_id="rp-listen-modal",
    )
    soup = BeautifulSoup(html, "html.parser")
    backdrop = soup.find(id="listen-modal-backdrop")
    assert backdrop is not None
    assert backdrop.get("aria-modal") == "false"
    assert soup.find(id="listen-btn-play") is not None
    assert soup.find(id="listen-btn-pause") is not None
    assert soup.find(id="listen-btn-stop") is not None
    assert soup.find(id="listen-segments") is not None
    assert soup.find(id="listen-elapsed") is not None
    assert soup.find(id="listen-total") is not None
    assert "IDLE" in html and "PLAYING" in html and "PAUSED" in html
    assert "pointer-events: none" in html  # floating dock wrapper
    assert "orientation: portrait" in html  # mobile portrait media query
    assert "listen-dock-open" in html
    assert soup.find(id="listen-player") is None
