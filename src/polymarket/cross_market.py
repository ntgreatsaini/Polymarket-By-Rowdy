"""Cross-market comparison — fetch probabilities from Kalshi, Metaculus, Manifold."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CrossMarketPrice:
    venue: str
    probability: float
    volume: float = 0.0
    last_updated: str = ""


@dataclass
class CrossMarketComparison:
    polymarket_price: float
    other_venues: list[CrossMarketPrice] = field(default_factory=list)
    avg_external_price: float = 0.0
    max_spread: float = 0.0

    @property
    def has_data(self) -> bool:
        return len(self.other_venues) > 0


class CrossMarketClient:
    """Fetch probabilities from competing prediction markets for comparison."""

    KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
    METACULUS_BASE = "https://www.metaculus.com/api2"
    MANIFOLD_BASE = "https://api.manifold.markets/v0"

    async def get_comparison(
        self, question: str, polymarket_price: float
    ) -> CrossMarketComparison:
        """Search competing venues for similar markets and return price comparison."""
        comparison = CrossMarketComparison(polymarket_price=polymarket_price)

        results = await self._search_all_venues(question)
        if results:
            comparison.other_venues = results
            prices = [r.probability for r in results]
            comparison.avg_external_price = sum(prices) / len(prices)
            all_prices = [polymarket_price] + prices
            comparison.max_spread = max(all_prices) - min(all_prices)

        return comparison

    async def _search_all_venues(self, question: str) -> list[CrossMarketPrice]:
        """Search Kalshi, Metaculus, and Manifold for similar markets."""
        venues: list[CrossMarketPrice] = []

        # Search keywords — take first 3 meaningful words
        keywords = self._extract_keywords(question)

        kalshi_result = await self._search_kalshi(keywords)
        if kalshi_result:
            venues.append(kalshi_result)

        metaculus_result = await self._search_metaculus(keywords)
        if metaculus_result:
            venues.append(metaculus_result)

        manifold_result = await self._search_manifold(keywords)
        if manifold_result:
            venues.append(manifold_result)

        return venues

    async def _search_kalshi(self, keywords: str) -> Optional[CrossMarketPrice]:
        """Search Kalshi for similar market."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.KALSHI_BASE}/markets",
                    params={"limit": 5, "status": "open"},
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()

            markets = data.get("markets", [])
            for m in markets:
                title = m.get("title", "").lower()
                if any(kw in title for kw in keywords.lower().split()):
                    yes_price = float(m.get("yes_ask", m.get("last_price", 0))) / 100
                    if 0.01 < yes_price < 0.99:
                        return CrossMarketPrice(
                            venue="Kalshi",
                            probability=yes_price,
                            volume=float(m.get("volume", 0)),
                        )
        except Exception as exc:
            logger.debug("kalshi_search_error", error=str(exc))
        return None

    async def _search_metaculus(self, keywords: str) -> Optional[CrossMarketPrice]:
        """Search Metaculus for similar question."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.METACULUS_BASE}/questions/",
                    params={
                        "search": keywords,
                        "status": "open",
                        "type": "forecast",
                        "limit": 5,
                    },
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()

            results = data.get("results", data if isinstance(data, list) else [])
            for q in results:
                community = q.get("community_prediction", {})
                prob = community.get("full", {}).get("q2")
                if prob is None:
                    prob = community.get("q2")
                if prob and 0.01 < float(prob) < 0.99:
                    return CrossMarketPrice(
                        venue="Metaculus",
                        probability=float(prob),
                    )
        except Exception as exc:
            logger.debug("metaculus_search_error", error=str(exc))
        return None

    async def _search_manifold(self, keywords: str) -> Optional[CrossMarketPrice]:
        """Search Manifold Markets for similar market."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.MANIFOLD_BASE}/search-markets",
                    params={"term": keywords, "sort": "score", "limit": 5},
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()

            markets = data if isinstance(data, list) else data.get("markets", [])
            for m in markets:
                prob = m.get("probability")
                if prob and 0.01 < float(prob) < 0.99:
                    return CrossMarketPrice(
                        venue="Manifold",
                        probability=float(prob),
                        volume=float(m.get("volume", 0)),
                    )
        except Exception as exc:
            logger.debug("manifold_search_error", error=str(exc))
        return None

    @staticmethod
    def _extract_keywords(question: str) -> str:
        """Extract meaningful keywords from question for cross-venue search."""
        stopwords = {
            "will", "the", "in", "by", "on", "to", "a", "an", "is", "be",
            "of", "for", "and", "or", "that", "this", "it", "at", "from",
            "with", "as", "are", "was", "were", "has", "have", "had", "do",
            "does", "did", "can", "could", "would", "should", "may", "might",
            "before", "after", "during", "above", "below", "between", "under",
            "over", "through", "into", "than", "more", "less", "what", "which",
            "who", "when", "where", "how", "if",
        }
        words = question.replace("?", "").replace("$", "").split()
        keywords = [w for w in words if w.lower() not in stopwords and len(w) > 2]
        return " ".join(keywords[:4])
