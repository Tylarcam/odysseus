"""Tests for LLM upstream retry/backoff helpers."""

from src.llm_core import (
    LLMConfig,
    _parse_retry_after,
    _retry_delay_seconds,
)


class _FakeHeaders(dict):
    pass


def test_parse_retry_after_seconds():
    assert _parse_retry_after(_FakeHeaders({"Retry-After": "15"})) == 15.0
    assert _parse_retry_after(_FakeHeaders({"retry-after": "3.5"})) == 3.5
    assert _parse_retry_after(_FakeHeaders()) is None
    assert _parse_retry_after(_FakeHeaders({"Retry-After": "soon"})) is None


def test_retry_delay_429_honors_retry_after():
    delay = _retry_delay_seconds(429, 1, _FakeHeaders({"Retry-After": "10"}))
    assert 10.0 <= delay <= 10.2


def test_retry_delay_429_exponential_without_header():
    d1 = _retry_delay_seconds(429, 1, None)
    d2 = _retry_delay_seconds(429, 2, None)
    d3 = _retry_delay_seconds(429, 3, None)
    assert 2.0 <= d1 <= 2.2
    assert 4.0 <= d2 <= 4.2
    assert 8.0 <= d3 <= 8.2


def test_retry_delay_429_caps_at_max():
    delay = _retry_delay_seconds(429, 10, None)
    assert delay <= LLMConfig.RATE_LIMIT_MAX_DELAY + 0.2


def test_retry_delay_503_lighter_than_429():
    assert _retry_delay_seconds(503, 1, None) < _retry_delay_seconds(429, 1, None)
