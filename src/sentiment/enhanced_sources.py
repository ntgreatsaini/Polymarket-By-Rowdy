"""Enhanced data sources — crypto fear & greed, Wikipedia current events, additional feeds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FearGreedData:
    value: int  # 0-100
    classification: str  # Extreme Fear, Fear, Neutral, Greed, Extreme Greed
    timestamp: str
    previous_value: int = 0
    trend: str = "stable"  # improving, declining, stable


@dataclass
class MarketBreadthData:
    """Aggregated market health indicators from multiple sources."""
    crypto_fear_greed: Optional[FearGreedData] = None
    bitcoin_dominance: float = 0.0
    total_crypto_market_cap: float = 0.0
    trending_topics: list[str] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.trending_topics is None:
            self.trending_topics = []


class EnhancedDataSources:
    """Fetch additional data from free APIs for better signal accuracy."""

    def __init__(self) -> None:
        self._timeout = httpx.Timeout(15.0)

    async def get_crypto_fear_greed(self) -> Optional[FearGreedData]:
        """Fetch Crypto Fear & Greed Index (free, no API key)."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    "https://api.alternative.me/fng/",
                    params={"limit": 2, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
                entries = data.get("data", [])
                if not entries:
                    return None

                current = entries[0]
                previous = entries[1] if len(entries) > 1 else {}

                value = int(current.get("value", 50))
                prev_value = int(previous.get("value", value))

                if value - prev_value > 5:
                    trend = "improving"
                elif prev_value - value > 5:
                    trend = "declining"
                else:
                    trend = "stable"

                return FearGreedData(
                    value=value,
                    classification=current.get("value_classification", "Neutral"),
                    timestamp=current.get("timestamp", ""),
                    previous_value=prev_value,
                    trend=trend,
                )
        except Exception as exc:
            logger.warning("fear_greed_error", error=str(exc))
            return None

    async def get_wikipedia_current_events(self) -> list[str]:
        """Fetch today's current events from Wikipedia (free, no API key)."""
        try:
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc)
            url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{today.month}/{today.day}"

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "PolymarketBot/1.0"},
                )
                resp.raise_for_status()
                data = resp.json()
                events = data.get("events", [])
                return [e.get("text", "") for e in events[:10] if e.get("text")]
        except Exception as exc:
            logger.warning("wikipedia_events_error", error=str(exc))
            return []

    async def get_polymarket_global_stats(self) -> dict[str, Any]:
        """Fetch Polymarket global volume and activity stats."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={"limit": 100, "order": "volume", "ascending": "false", "active": "true"},
                )
                resp.raise_for_status()
                markets = resp.json()

                total_volume = sum(float(m.get("volume", 0) or 0) for m in markets)
                total_liquidity = sum(float(m.get("liquidity", 0) or 0) for m in markets)
                active_count = len(markets)

                categories: dict[str, int] = {}
                for m in markets:
                    tags = m.get("tags", []) or []
                    for tag in tags[:1]:
                        t = tag.get("label", "Other") if isinstance(tag, dict) else str(tag)
                        categories[t] = categories.get(t, 0) + 1

                return {
                    "total_volume_top100": total_volume,
                    "total_liquidity_top100": total_liquidity,
                    "active_markets_sampled": active_count,
                    "top_categories": dict(sorted(categories.items(), key=lambda x: -x[1])[:5]),
                }
        except Exception as exc:
            logger.warning("polymarket_stats_error", error=str(exc))
            return {}

    async def get_market_breadth(self) -> MarketBreadthData:
        """Aggregate multiple data sources for market context."""
        from src.config.settings import get_settings
        settings = get_settings()

        breadth = MarketBreadthData()

        fear_greed = await self.get_crypto_fear_greed()
        if fear_greed:
            breadth.crypto_fear_greed = fear_greed

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                if settings.coingecko_api_key:
                    headers = {"x-cg-demo-api-key": settings.coingecko_api_key}
                else:
                    headers = {}
                resp = await client.get(
                    f"{settings.coingecko_base_url}/global",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    breadth.bitcoin_dominance = data.get("market_cap_percentage", {}).get("btc", 0)
                    breadth.total_crypto_market_cap = data.get("total_market_cap", {}).get("usd", 0)
        except Exception as exc:
            logger.warning("coingecko_global_error", error=str(exc))

        return breadth

    async def get_additional_rss_news(self, query: str, max_articles: int = 10) -> list[dict[str, str]]:
        """Fetch additional news from more RSS feeds."""
        import feedparser

        feeds = [
            f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        ]

        articles: list[dict[str, str]] = []
        for feed_url in feeds:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(feed_url, headers={"User-Agent": "PolymarketBot/1.0"})
                    if resp.status_code != 200:
                        continue
                    parsed = feedparser.parse(resp.text)
                    for entry in parsed.entries[:max_articles]:
                        articles.append({
                            "title": entry.get("title", ""),
                            "source": parsed.feed.get("title", "RSS"),
                            "url": entry.get("link", ""),
                            "summary": entry.get("summary", "")[:200],
                        })
            except Exception:
                continue

        return articles[:max_articles]
