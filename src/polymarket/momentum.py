"""Market momentum tracker — price history, trend detection, order book analysis."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

from src.polymarket.client import PolymarketClient

logger = structlog.get_logger(__name__)


@dataclass
class MomentumData:
    condition_id: str
    change_1h: float = 0.0
    change_6h: float = 0.0
    change_24h: float = 0.0
    trend: str = "neutral"  # bullish, bearish, neutral
    volatility: str = "low"  # low, medium, high
    price_history: list[tuple[float, float]] = field(default_factory=list)
    order_book_imbalance: float = 0.0  # -1 (sell heavy) to +1 (buy heavy)
    spread: float = 0.0
    depth_score: float = 0.0  # 0-1, how deep the order book is


@dataclass
class OrderBookAnalysis:
    bid_depth: float
    ask_depth: float
    spread: float
    imbalance: float  # -1 (sell wall) to +1 (buy wall)
    depth_score: float  # 0-1 normalized
    manipulation_risk: float  # 0-1
    top_bid: float
    top_ask: float


class MomentumTracker:
    """Track price momentum and order book depth for markets."""

    def __init__(self, poly_client: PolymarketClient) -> None:
        self._poly = poly_client
        self._price_cache: dict[str, list[tuple[float, float]]] = defaultdict(list)
        self._max_history = 288  # ~24h at 5-min intervals

    def record_price(self, condition_id: str, price: float) -> None:
        """Record a price point for momentum tracking."""
        now = time.time()
        history = self._price_cache[condition_id]
        history.append((now, price))
        if len(history) > self._max_history:
            self._price_cache[condition_id] = history[-self._max_history:]

    def get_momentum(self, condition_id: str, current_price: float) -> MomentumData:
        """Calculate momentum indicators for a market."""
        history = self._price_cache.get(condition_id, [])
        now = time.time()

        self.record_price(condition_id, current_price)

        change_1h = self._calc_change(history, now, 3600, current_price)
        change_6h = self._calc_change(history, now, 21600, current_price)
        change_24h = self._calc_change(history, now, 86400, current_price)

        trend = self._detect_trend(change_1h, change_6h, change_24h)
        volatility = self._assess_volatility(history, now)

        return MomentumData(
            condition_id=condition_id,
            change_1h=round(change_1h, 4),
            change_6h=round(change_6h, 4),
            change_24h=round(change_24h, 4),
            trend=trend,
            volatility=volatility,
            price_history=history[-20:],
        )

    async def analyze_order_book(self, token_id: str) -> OrderBookAnalysis:
        """Analyze order book depth and detect manipulation risk."""
        try:
            book = await self._poly.get_order_book(token_id)
        except Exception as exc:
            logger.warning("order_book_fetch_failed", error=str(exc))
            return OrderBookAnalysis(
                bid_depth=0, ask_depth=0, spread=0.05,
                imbalance=0, depth_score=0, manipulation_risk=0.5,
                top_bid=0, top_ask=0,
            )

        bids = book.get("bids", [])
        asks = book.get("asks", [])

        bid_depth = sum(float(b.get("size", 0)) for b in bids[:20])
        ask_depth = sum(float(a.get("size", 0)) for a in asks[:20])

        top_bid = float(bids[0]["price"]) if bids else 0.0
        top_ask = float(asks[0]["price"]) if asks else 1.0
        spread = top_ask - top_bid

        total_depth = bid_depth + ask_depth
        if total_depth > 0:
            imbalance = (bid_depth - ask_depth) / total_depth
        else:
            imbalance = 0.0

        depth_score = min(1.0, total_depth / 50000.0)

        manipulation_risk = 0.0
        if depth_score < 0.1:
            manipulation_risk += 0.4
        if spread > 0.05:
            manipulation_risk += 0.3
        if abs(imbalance) > 0.7:
            manipulation_risk += 0.2
        if self._detect_spoofing(bids, asks):
            manipulation_risk += 0.3
        manipulation_risk = min(1.0, manipulation_risk)

        return OrderBookAnalysis(
            bid_depth=round(bid_depth, 2),
            ask_depth=round(ask_depth, 2),
            spread=round(spread, 4),
            imbalance=round(imbalance, 4),
            depth_score=round(depth_score, 4),
            manipulation_risk=round(manipulation_risk, 4),
            top_bid=round(top_bid, 4),
            top_ask=round(top_ask, 4),
        )

    @staticmethod
    def _calc_change(
        history: list[tuple[float, float]],
        now: float,
        window_secs: float,
        current_price: float,
    ) -> float:
        target_time = now - window_secs
        closest: Optional[tuple[float, float]] = None
        for ts, price in history:
            if ts <= target_time:
                if closest is None or ts > closest[0]:
                    closest = (ts, price)

        if closest is None or closest[1] == 0:
            return 0.0
        return (current_price - closest[1]) / closest[1]

    @staticmethod
    def _detect_trend(change_1h: float, change_6h: float, change_24h: float) -> str:
        bullish_signals = sum([
            change_1h > 0.02,
            change_6h > 0.03,
            change_24h > 0.05,
        ])
        bearish_signals = sum([
            change_1h < -0.02,
            change_6h < -0.03,
            change_24h < -0.05,
        ])

        if bullish_signals >= 2:
            return "bullish"
        elif bearish_signals >= 2:
            return "bearish"
        return "neutral"

    @staticmethod
    def _assess_volatility(history: list[tuple[float, float]], now: float) -> str:
        recent = [p for ts, p in history if now - ts < 3600]
        if len(recent) < 3:
            return "unknown"

        avg = sum(recent) / len(recent)
        if avg == 0:
            return "low"
        variance = sum((p - avg) ** 2 for p in recent) / len(recent)
        cv = (variance ** 0.5) / avg

        if cv > 0.1:
            return "high"
        elif cv > 0.03:
            return "medium"
        return "low"

    @staticmethod
    def _detect_spoofing(bids: list[dict], asks: list[dict]) -> bool:
        """Detect potential spoofing — large orders far from mid price."""
        if len(bids) < 5 or len(asks) < 5:
            return False

        mid = (float(bids[0].get("price", 0)) + float(asks[0].get("price", 1))) / 2
        for order in bids[5:] + asks[5:]:
            size = float(order.get("size", 0))
            price = float(order.get("price", 0))
            distance = abs(price - mid)
            if size > 5000 and distance > 0.1:
                return True
        return False
