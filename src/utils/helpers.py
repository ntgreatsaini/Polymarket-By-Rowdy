"""Shared utility functions."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def hash_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def format_usd(amount: float) -> str:
    if abs(amount) >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if abs(amount) >= 1_000:
        return f"${amount / 1_000:.1f}K"
    return f"${amount:,.2f}"


def format_pct(value: float) -> str:
    return f"{value:.1%}"


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return default
