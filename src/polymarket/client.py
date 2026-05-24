"""Polymarket API client for fetching live market data."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class PolymarketClient:
    """Async client for Polymarket Gamma, Data, and CLOB APIs."""

    def __init__(self) -> None:
        settings = get_settings()
        self.gamma_url = settings.polymarket_gamma_api
        self.data_url = settings.polymarket_data_api
        self.clob_url = settings.polymarket_clob_api
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── Gamma API ──────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        active: bool = True,
        closed: bool = False,
        order: str = "volume",
        ascending: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch markets from the Gamma API."""
        client = await self._get_client()
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower(),
        }
        resp = await client.get(f"{self.gamma_url}/markets", params=params)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_market_by_id(self, condition_id: str) -> dict[str, Any]:
        """Fetch a single market by condition ID."""
        client = await self._get_client()
        resp = await client.get(f"{self.gamma_url}/markets/{condition_id}")
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def search_markets(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search markets by keyword."""
        client = await self._get_client()
        params = {"_q": query, "limit": limit, "active": "true"}
        resp = await client.get(f"{self.gamma_url}/markets", params=params)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_events(self, limit: int = 50, active: bool = True) -> list[dict[str, Any]]:
        """Fetch events from the Gamma API."""
        client = await self._get_client()
        params = {"limit": limit, "active": str(active).lower()}
        resp = await client.get(f"{self.gamma_url}/events", params=params)
        resp.raise_for_status()
        return resp.json()

    # ── CLOB API ───────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_order_book(self, token_id: str) -> dict[str, Any]:
        """Fetch order book for a market token."""
        client = await self._get_client()
        resp = await client.get(f"{self.clob_url}/book", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_market_price(self, token_id: str) -> dict[str, Any]:
        """Fetch current price for a market token."""
        client = await self._get_client()
        resp = await client.get(f"{self.clob_url}/price", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_midpoint(self, token_id: str) -> dict[str, Any]:
        """Fetch midpoint price for a market token."""
        client = await self._get_client()
        resp = await client.get(f"{self.clob_url}/midpoint", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_last_trades(
        self, market_id: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Fetch recent trades, optionally filtered by market."""
        client = await self._get_client()
        params: dict[str, Any] = {"limit": limit}
        if market_id:
            params["market"] = market_id
        resp = await client.get(f"{self.clob_url}/trades", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("data", [])

    # ── Helpers ────────────────────────────────────────

    @staticmethod
    def parse_market(raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw Gamma API market response."""
        tokens = raw.get("tokens", []) or raw.get("clobTokenIds", [])
        yes_price = 0.0
        no_price = 0.0

        if isinstance(tokens, list) and tokens:
            for t in tokens:
                if isinstance(t, dict):
                    outcome = t.get("outcome", "").upper()
                    price = float(t.get("price", 0) or 0)
                    if outcome == "YES":
                        yes_price = price
                    elif outcome == "NO":
                        no_price = price

        if yes_price == 0 and no_price == 0:
            best_bid = raw.get("bestBid")
            best_ask = raw.get("bestAsk")
            if best_bid is not None and best_ask is not None:
                yes_price = (float(best_bid) + float(best_ask)) / 2
                no_price = 1.0 - yes_price
            outcome_prices = raw.get("outcomePrices")
            if outcome_prices and isinstance(outcome_prices, (list, str)):
                if isinstance(outcome_prices, str):
                    import json
                    try:
                        outcome_prices = json.loads(outcome_prices)
                    except (json.JSONDecodeError, ValueError):
                        outcome_prices = []
                if isinstance(outcome_prices, list) and len(outcome_prices) >= 2:
                    yes_price = float(outcome_prices[0])
                    no_price = float(outcome_prices[1])

        volume_raw = raw.get("volume", 0) or raw.get("volumeNum", 0) or 0
        liquidity_raw = raw.get("liquidity", 0) or raw.get("liquidityNum", 0) or 0

        end_date = None
        end_str = raw.get("endDate") or raw.get("end_date_iso")
        if end_str:
            try:
                end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return {
            "condition_id": raw.get("conditionId") or raw.get("condition_id") or str(raw.get("id", "")),
            "question": raw.get("question", raw.get("title", "Unknown")),
            "slug": raw.get("slug", ""),
            "category": _classify_category(raw),
            "yes_price": round(yes_price, 4),
            "no_price": round(no_price, 4),
            "volume": float(volume_raw),
            "liquidity": float(liquidity_raw),
            "is_active": raw.get("active", True),
            "end_date": end_date,
            "tags": raw.get("tags", []),
            "tokens": tokens,
        }

    async def get_all_active_markets(self, max_pages: int = 10) -> list[dict[str, Any]]:
        """Paginate through all active markets."""
        all_markets: list[dict[str, Any]] = []
        limit = 100
        for page in range(max_pages):
            batch = await self.get_markets(limit=limit, offset=page * limit)
            if not batch:
                break
            all_markets.extend(batch)
            if len(batch) < limit:
                break
        logger.info("fetched_markets", count=len(all_markets))
        return all_markets


def _classify_category(raw: dict[str, Any]) -> str:
    """Classify market category from tags or title keywords."""
    tags = [t.lower() if isinstance(t, str) else "" for t in (raw.get("tags") or [])]
    question = (raw.get("question") or raw.get("title") or "").lower()
    combined = " ".join(tags) + " " + question

    if any(kw in combined for kw in ("bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "token", "defi")):
        return "crypto"
    if any(kw in combined for kw in ("election", "president", "senate", "congress", "vote", "trump", "biden", "political", "governor")):
        return "politics"
    if any(kw in combined for kw in ("nba", "nfl", "mlb", "soccer", "football", "tennis", "sport", "championship", "world cup", "super bowl")):
        return "sports"
    if any(kw in combined for kw in ("ai", "openai", "gpt", "artificial intelligence", "technology", "apple", "google", "microsoft")):
        return "ai_tech"
    if any(kw in combined for kw in ("fed", "inflation", "gdp", "economy", "recession", "interest rate", "cpi", "unemployment")):
        return "macro"
    return "other"
