"""Tests for Market Momentum Tracker."""

import time

from src.polymarket.momentum import MomentumTracker


class FakePoly:
    pass


def test_record_and_get_momentum():
    tracker = MomentumTracker(FakePoly())  # type: ignore
    cid = "test-market"

    # Record some prices
    now = time.time()
    tracker._price_cache[cid] = [
        (now - 7200, 0.40),   # 2h ago
        (now - 3600, 0.42),   # 1h ago
        (now - 1800, 0.44),   # 30m ago
    ]

    momentum = tracker.get_momentum(cid, 0.48)
    assert momentum.condition_id == cid
    assert momentum.change_1h > 0  # price went up
    assert momentum.trend in ("bullish", "bearish", "neutral")


def test_detect_trend():
    assert MomentumTracker._detect_trend(0.05, 0.05, 0.1) == "bullish"
    assert MomentumTracker._detect_trend(-0.05, -0.05, -0.1) == "bearish"
    assert MomentumTracker._detect_trend(0.001, 0.001, 0.001) == "neutral"


def test_assess_volatility():
    now = time.time()
    # Low volatility - all same price
    low_vol = [(now - i * 60, 0.50) for i in range(10)]
    assert MomentumTracker._assess_volatility(low_vol, now) == "low"


def test_spoofing_detection():
    # No spoofing with normal orders
    bids = [{"price": "0.50", "size": "100"} for _ in range(10)]
    asks = [{"price": "0.51", "size": "100"} for _ in range(10)]
    assert not MomentumTracker._detect_spoofing(bids, asks)

    # Spoofing: large order far from mid
    bids_spoof = [{"price": "0.50", "size": "100"} for _ in range(10)]
    bids_spoof[7] = {"price": "0.30", "size": "10000"}
    asks_spoof = [{"price": "0.51", "size": "100"} for _ in range(10)]
    assert MomentumTracker._detect_spoofing(bids_spoof, asks_spoof)
