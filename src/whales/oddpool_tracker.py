"""OddPool API integration for whale tracking and arbitrage detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class OddPoolWhaleTrade:
    platform: str
    event_title: str
    market_title: str
    outcome: str
    timestamp: datetime
    taker_side: str
    trade_size_usd: float
    price: float
    count: int = 1


@dataclass
class OddPoolWhaleStats:
    total_volume_24h: float
    total_trades_24h: int
    avg_trade_size: float
    top_trades: list[OddPoolWhaleTrade] = field(default_factory=list)


@dataclass
class ArbitrageOpportunity:
    event_title: str
    venue_a: str
    venue_b: str
    side_a: str
    side_b: str
    price_a: float
    price_b: float
    gross_spread_cents: float
    net_profit_cents: float
    last_seen: str


class OddPoolTracker:
    """Track whale trades and arbitrage opportunities via OddPool API."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._api_key = self._settings.oddpool_api_key
        self._base_url = self._settings.oddpool_base_url

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def get_whale_feed(
        self,
        limit: int = 20,
        platform: str = "polymarket",
        min_size: Optional[float] = None,
    ) -> OddPoolWhaleStats:
        """Get whale trade feed from OddPool."""
        if not self.is_configured:
            return OddPoolWhaleStats(
                total_volume_24h=0, total_trades_24h=0, avg_trade_size=0
            )

        params: dict[str, Any] = {"limit": limit, "platform": platform}
        if min_size:
            params["min_size"] = min_size

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self._base_url}/whales/user/feed",
                    headers={"X-API-Key": self._api_key},
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

            trades: list[OddPoolWhaleTrade] = []
            for t in data.get("trades", []):
                ts = datetime.now(timezone.utc)
                ts_raw = t.get("timestamp")
                if ts_raw:
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass
                trades.append(
                    OddPoolWhaleTrade(
                        platform=t.get("platform", "unknown"),
                        event_title=t.get("event_title", ""),
                        market_title=t.get("market_title", ""),
                        outcome=t.get("outcome", ""),
                        timestamp=ts,
                        taker_side=t.get("taker_side", ""),
                        trade_size_usd=float(t.get("trade_size_usd", 0)),
                        price=float(t.get("price", 0)),
                        count=int(t.get("count", 1)),
                    )
                )

            stats = data.get("stats", {})
            return OddPoolWhaleStats(
                total_volume_24h=float(stats.get("total_volume_24h", 0)),
                total_trades_24h=int(stats.get("total_trades_24h", 0)),
                avg_trade_size=float(stats.get("avg_trade_size", 0)),
                top_trades=sorted(trades, key=lambda x: x.trade_size_usd, reverse=True)[:10],
            )
        except httpx.HTTPStatusError as exc:
            logger.warning("oddpool_whale_feed_error", status=exc.response.status_code)
            return OddPoolWhaleStats(
                total_volume_24h=0, total_trades_24h=0, avg_trade_size=0
            )
        except Exception as exc:
            logger.warning("oddpool_whale_feed_error", error=str(exc))
            return OddPoolWhaleStats(
                total_volume_24h=0, total_trades_24h=0, avg_trade_size=0
            )

    async def get_whale_stats(self, period: str = "24h") -> dict[str, Any]:
        """Get aggregated whale statistics."""
        if not self.is_configured:
            return {}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self._base_url}/whales/user/stats",
                    headers={"X-API-Key": self._api_key},
                    params={"period": period},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("oddpool_whale_stats_error", error=str(exc))
            return {}

    async def get_arbitrage_opportunities(
        self, min_net_cents: float = 0.5, minutes: int = 30
    ) -> list[ArbitrageOpportunity]:
        """Find cross-venue arbitrage opportunities between Polymarket and Kalshi."""
        if not self.is_configured:
            return []

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self._base_url}/arbitrage/current",
                    headers={"X-API-Key": self._api_key},
                    params={"min_net_cents": min_net_cents, "minutes": minutes},
                )
                resp.raise_for_status()
                data = resp.json()

            opportunities: list[ArbitrageOpportunity] = []
            for opp in data.get("opportunities", data if isinstance(data, list) else []):
                opportunities.append(
                    ArbitrageOpportunity(
                        event_title=opp.get("event_title", ""),
                        venue_a=opp.get("venue_a", ""),
                        venue_b=opp.get("venue_b", ""),
                        side_a=opp.get("side_a", ""),
                        side_b=opp.get("side_b", ""),
                        price_a=float(opp.get("price_a", 0)),
                        price_b=float(opp.get("price_b", 0)),
                        gross_spread_cents=float(opp.get("gross_spread_cents", 0)),
                        net_profit_cents=float(opp.get("net_profit_cents", 0)),
                        last_seen=opp.get("last_seen", ""),
                    )
                )
            logger.info("oddpool_arbitrage_found", count=len(opportunities))
            return opportunities
        except httpx.HTTPStatusError as exc:
            logger.warning("oddpool_arbitrage_error", status=exc.response.status_code)
            return []
        except Exception as exc:
            logger.warning("oddpool_arbitrage_error", error=str(exc))
            return []

    async def search_markets(
        self, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search prediction markets across Polymarket and Kalshi."""
        if not self.is_configured:
            return []

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self._base_url}/search/markets",
                    headers={"X-API-Key": self._api_key},
                    params={"q": query, "limit": limit},
                )
                resp.raise_for_status()
                data = resp.json()
            return data.get("markets", data if isinstance(data, list) else [])
        except Exception as exc:
            logger.warning("oddpool_search_error", error=str(exc))
            return []

    def format_whale_summary(self, stats: OddPoolWhaleStats) -> str:
        """Format whale stats for Telegram message inclusion."""
        if not stats.top_trades:
            return ""
        lines = [f"[OddPool] 24h Volume: ${stats.total_volume_24h:,.0f} | Trades: {stats.total_trades_24h}"]
        for t in stats.top_trades[:3]:
            lines.append(
                f"  {t.taker_side.upper()} ${t.trade_size_usd:,.0f} @ {t.price:.2f} — {t.event_title[:50]}"
            )
        return "\n".join(lines)
