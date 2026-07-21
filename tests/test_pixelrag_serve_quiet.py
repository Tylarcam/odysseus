"""Tests for quiet PixelRAG serve wrapper."""

from __future__ import annotations

import logging

from tools.pixelrag_serve_quiet import _configure_plain_logging


def test_configure_plain_logging_uses_plain_format() -> None:
    _configure_plain_logging()
    root = logging.getLogger()
    assert root.handlers
    formatter = root.handlers[0].formatter
    assert formatter is not None
    format_str = formatter._style._fmt  # noqa: SLF001
    assert "%(req)s" not in format_str
    assert "%(message)s" in format_str
