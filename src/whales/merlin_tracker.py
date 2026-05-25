"""Merlin analytics integration for smart-money tracking and insider detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class MerlinTrader:
    wallet: str
    pnl: float
    roi: float
    win_rate: float
    volume: float
    rank: int
    category: str = "overall"
    trader_score: float = 0.0
    is_insider: bool = False


@dataclass
class MerlinInsider:
    wallet: str
    insider_score: float
    pnl: float
    roi: float
    recent_trades: int
    categories: list[str] = field(default_factory=list)


@dataclass
class MerlinMarketData:
    top_traders: list[MerlinTrader] = field(default_factory=list)
    insiders: list[MerlinInsider] = field(default_factory=list)
    smart_money_bias: str = "neutral"
    smart_money_confidence: float = 0.0


class MerlinTracker:
    """Track top traders and insiders via Merlin analytics platform."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._base_url = self._settings.merlin_base_url
        self._cache: dict[str, Any] = {}

    async def get_top_traders(
        self,
        category: str = "OVERALL",
        time_period: str = "WEEK",
        order_by: str = "PNL",
        limit: int = 25,
    ) -> list[MerlinTrader]:
        """Fetch top traders from Polymarket Data API leaderboard (same data Merlin uses)."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://data-api.polymarket.com/v1/leaderboard",
                    params={
                        "category": category.upper(),
                        "timePeriod": time_period.upper(),
                        "orderBy": order_by.upper(),
                        "limit": limit,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            traders: list[MerlinTrader] = []
            entries = data if isinstance(data, list) else data.get("leaderboard", [])
            for i, entry in enumerate(entries, 1):
                pnl = float(entry.get("pnl", entry.get("profit", 0)))
                volume = float(entry.get("vol", entry.get("volume", entry.get("totalVolume", 0))))
                # Estimate win rate from PnL/volume ratio if not provided
                win_rate = float(entry.get("winRate", entry.get("win_rate", 0)))
                if win_rate == 0 and volume > 0 and pnl > 0:
                    win_rate = min(0.95, 0.5 + (pnl / volume) * 0.5)
                traders.append(
                    MerlinTrader(
                        wallet=entry.get("proxyWallet", entry.get("userAddress", entry.get("address", ""))),
                        pnl=pnl,
                        roi=float(entry.get("roi", 0)),
                        win_rate=win_rate,
                        volume=volume,
                        rank=int(entry.get("rank", i)),
                        category=category.lower(),
                        trader_score=float(entry.get("traderScore", entry.get("score", 0))),
                    )
                )
            logger.info("merlin_top_traders", count=len(traders), category=category)
            return traders
        except Exception as exc:
            logger.warning("merlin_top_traders_error", error=str(exc))
            return []

    async def get_insiders(self, limit: int = 20) -> list[MerlinInsider]:
        """Identify insider/smart-money traders who consistently profit on unlikely outcomes."""
        try:
            traders = await self.get_top_traders(
                category="OVERALL", time_period="MONTH", order_by="PNL", limit=50
            )
            insiders: list[MerlinInsider] = []
            for t in traders:
                # High PnL with good win rate or high PnL/volume ratio
                is_insider = (
                    (t.win_rate > 0.60 and t.pnl > 5000)
                    or (t.pnl > 50000 and t.volume > 0 and t.pnl / t.volume > 0.15)
                )
                if is_insider:
                    score = min(1.0, t.pnl / 100000) * max(0.5, t.win_rate)
                    insiders.append(
                        MerlinInsider(
                            wallet=t.wallet,
                            insider_score=round(score, 3),
                            pnl=t.pnl,
                            roi=t.roi,
                            recent_trades=0,
                            categories=[t.category],
                        )
                    )
            insiders.sort(key=lambda x: x.insider_score, reverse=True)
            return insiders[:limit]
        except Exception as exc:
            logger.warning("merlin_insiders_error", error=str(exc))
            return []

    async def get_smart_money_signal(
        self, category: str = "OVERALL"
    ) -> MerlinMarketData:
        """Get smart money consensus direction from top traders."""
        try:
            traders = await self.get_top_traders(
                category=category, time_period="WEEK", order_by="PNL", limit=25
            )
            insiders = await self.get_insiders(limit=10)

            if not traders:
                return MerlinMarketData()

            profitable = [t for t in traders if t.pnl > 0]
            losing = [t for t in traders if t.pnl < 0]

            profit_volume = sum(t.volume for t in profitable)
            loss_volume = sum(t.volume for t in losing)
            total_volume = profit_volume + loss_volume

            if total_volume == 0:
                bias = "neutral"
                confidence = 0.0
            elif profit_volume > loss_volume * 1.5:
                bias = "bullish"
                confidence = min(1.0, profit_volume / (total_volume + 1))
            elif loss_volume > profit_volume * 1.5:
                bias = "bearish"
                confidence = min(1.0, loss_volume / (total_volume + 1))
            else:
                bias = "neutral"
                confidence = 0.3

            avg_win_rate = (
                sum(t.win_rate for t in traders[:10]) / min(10, len(traders))
                if traders
                else 0
            )
            confidence = confidence * avg_win_rate if avg_win_rate > 0 else confidence

            return MerlinMarketData(
                top_traders=traders[:10],
                insiders=insiders,
                smart_money_bias=bias,
                smart_money_confidence=round(confidence, 3),
            )
        except Exception as exc:
            logger.warning("merlin_smart_money_error", error=str(exc))
            return MerlinMarketData()

    def format_smart_money_summary(self, data: MerlinMarketData) -> str:
        """Format Merlin data for signal inclusion."""
        if not data.top_traders:
            return ""
        lines = [
            f"[Merlin] Smart Money: {data.smart_money_bias.title()} "
            f"(confidence: {data.smart_money_confidence:.0%})"
        ]
        if data.top_traders[:3]:
            lines.append("Top Traders (week):")
            for t in data.top_traders[:3]:
                addr = t.wallet[:8] + "..." if len(t.wallet) > 8 else t.wallet
                lines.append(
                    f"  #{t.rank} {addr} | PnL: ${t.pnl:,.0f} | WR: {t.win_rate:.0%}"
                )
        if data.insiders[:2]:
            lines.append("Insiders detected:")
            for ins in data.insiders[:2]:
                addr = ins.wallet[:8] + "..." if len(ins.wallet) > 8 else ins.wallet
                lines.append(
                    f"  {addr} | Score: {ins.insider_score:.2f} | PnL: ${ins.pnl:,.0f}"
                )
        return "\n".join(lines)
