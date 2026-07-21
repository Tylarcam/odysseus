"""Tests for handoff JD materialization."""

from __future__ import annotations

import os
import tempfile

import pytest

from src.handoff_materialize import (
    extract_jd_section,
    folder_slug_from_handoff,
    is_handoff_document,
    materialize_handoff_jd,
    maybe_materialize_handoff_jd,
)


def test_is_handoff_document():
    assert is_handoff_document("handoff → claude: Microdose Movement")
    assert not is_handoff_document("Random doc")


def test_extract_jd_section():
    body = "## Goal\n\nDo thing\n\n## Full job description\n\n**Employer:** Acme\n\nBody here."
    assert "Employer" in extract_jd_section(body)


def test_folder_slug_from_handoff():
    slug = folder_slug_from_handoff(
        "handoff → claude: Microdose Movement — Agentic AI Internship (Handshake 11107812)"
    )
    assert slug.startswith("MicrodoseMovement_")
    assert slug.endswith("_2026-06") or "_202" in slug


def test_materialize_handoff_jd_writes_files():
    content = """---
handoff_version: 1
source: cursor
target: claude
status: pending
project: C:\\Users\\tylar\\code
---

## Goal

Review role

## Full job description

**Employer:** Test Co
**Title:** Agent Builder
"""
    with tempfile.TemporaryDirectory() as tmp:
        result = materialize_handoff_jd(
            doc_id="abc-123",
            title="handoff → claude: Test Co — Agent Builder",
            content=content,
            job_app_root=tmp,
        )
        assert result["ok"] is True
        assert os.path.isfile(result["jd_path"])
        with open(result["jd_path"], encoding="utf-8") as fh:
            text = fh.read()
        assert "Test Co" in text
        assert os.path.isfile(result["meta_path"])


def test_maybe_materialize_skips_non_handoff():
    assert (
        maybe_materialize_handoff_jd(
            doc_id="x",
            title="Regular note",
            content="no jd here",
        )
        is None
    )
