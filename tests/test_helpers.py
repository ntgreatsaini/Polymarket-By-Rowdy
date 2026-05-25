"""Tests for utility helpers."""

from src.utils.helpers import format_pct, format_usd, safe_float, truncate


def test_truncate():
    assert truncate("hello", 10) == "hello"
    assert len(truncate("a" * 300, 50)) == 50


def test_format_usd():
    assert format_usd(1500000) == "$1.5M"
    assert format_usd(45000) == "$45.0K"
    assert format_usd(99.5) == "$99.50"


def test_format_pct():
    assert format_pct(0.753) == "75.3%"


def test_safe_float():
    assert safe_float("3.14") == 3.14
    assert safe_float(None, 0.0) == 0.0
    assert safe_float("bad", 1.0) == 1.0
