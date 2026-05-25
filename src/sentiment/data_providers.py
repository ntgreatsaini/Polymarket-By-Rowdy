"""External data providers: CoinGecko, FRED, The Odds API, Yahoo Finance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


# ── CoinGecko ──────────────────────────────────────────


@dataclass
class CryptoData:
    symbol: str
    price_usd: float
    price_change_24h: float
    market_cap: float
    volume_24h: float
    ath: float
    ath_change_pct: float


class CoinGeckoProvider:
    """Fetch crypto market data from CoinGecko API."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.coingecko_base_url
        self._api_key = settings.coingecko_api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {"Accept": "application/json"}
            if self._api_key:
                headers["x-cg-demo-api-key"] = self._api_key
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0),
                headers=headers,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_price(self, coin_id: str = "bitcoin") -> Optional[CryptoData]:
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self._base_url}/coins/{coin_id}",
                params={"localization": "false", "sparkline": "false"},
            )
            resp.raise_for_status()
            data = resp.json()
            md = data.get("market_data", {})
            return CryptoData(
                symbol=data.get("symbol", coin_id).upper(),
                price_usd=md.get("current_price", {}).get("usd", 0),
                price_change_24h=md.get("price_change_percentage_24h", 0),
                market_cap=md.get("market_cap", {}).get("usd", 0),
                volume_24h=md.get("total_volume", {}).get("usd", 0),
                ath=md.get("ath", {}).get("usd", 0),
                ath_change_pct=md.get("ath_change_percentage", {}).get("usd", 0),
            )
        except Exception as exc:
            logger.warning("coingecko_error", error=str(exc), coin=coin_id)
            return None

    async def get_trending(self) -> list[dict[str, Any]]:
        try:
            client = await self._get_client()
            resp = await client.get(f"{self._base_url}/search/trending")
            resp.raise_for_status()
            data = resp.json()
            return [c.get("item", {}) for c in data.get("coins", [])]
        except Exception as exc:
            logger.warning("coingecko_trending_error", error=str(exc))
            return []

    async def get_market_chart(
        self, coin_id: str = "bitcoin", days: int = 7
    ) -> list[list[float]]:
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self._base_url}/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": str(days)},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("prices", [])
        except Exception as exc:
            logger.warning("coingecko_chart_error", error=str(exc))
            return []


# ── FRED ───────────────────────────────────────────────


@dataclass
class EconomicIndicator:
    series_id: str
    title: str
    value: float
    date: str
    units: str


class FREDProvider:
    """Fetch economic data from Federal Reserve Economic Data (FRED)."""

    BASE_URL = "https://api.stlouisfed.org/fred"

    def __init__(self) -> None:
        self._api_key = get_settings().fred_api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_series(self, series_id: str) -> Optional[EconomicIndicator]:
        if not self._api_key:
            return None
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.BASE_URL}/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": self._api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": "1",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            obs = data.get("observations", [])
            if not obs:
                return None

            info_resp = await client.get(
                f"{self.BASE_URL}/series",
                params={
                    "series_id": series_id,
                    "api_key": self._api_key,
                    "file_type": "json",
                },
            )
            info_resp.raise_for_status()
            info = info_resp.json().get("seriess", [{}])[0]

            return EconomicIndicator(
                series_id=series_id,
                title=info.get("title", series_id),
                value=float(obs[0].get("value", 0)),
                date=obs[0].get("date", ""),
                units=info.get("units", ""),
            )
        except Exception as exc:
            logger.warning("fred_error", error=str(exc), series=series_id)
            return None

    async def get_key_indicators(self) -> dict[str, Optional[EconomicIndicator]]:
        indicators = {
            "CPI": "CPIAUCSL",
            "Unemployment": "UNRATE",
            "GDP": "GDP",
            "Fed_Funds_Rate": "FEDFUNDS",
            "10Y_Treasury": "DGS10",
        }
        results: dict[str, Optional[EconomicIndicator]] = {}
        for name, series_id in indicators.items():
            results[name] = await self.get_series(series_id)
        return results


# ── The Odds API ───────────────────────────────────────


@dataclass
class SportsOdds:
    sport: str
    event: str
    commence_time: str
    home_team: str
    away_team: str
    bookmaker_odds: list[dict[str, Any]]


class OddsAPIProvider:
    """Fetch sports betting odds from The Odds API."""

    BASE_URL = "https://api.the-odds-api.com/v4"

    def __init__(self) -> None:
        self._api_key = get_settings().the_odds_api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_sports(self) -> list[dict[str, Any]]:
        if not self._api_key:
            return []
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.BASE_URL}/sports",
                params={"apiKey": self._api_key},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("odds_api_sports_error", error=str(exc))
            return []

    async def get_odds(
        self, sport_key: str = "upcoming", regions: str = "us", markets: str = "h2h"
    ) -> list[SportsOdds]:
        if not self._api_key:
            return []
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.BASE_URL}/sports/{sport_key}/odds",
                params={
                    "apiKey": self._api_key,
                    "regions": regions,
                    "markets": markets,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results: list[SportsOdds] = []
            for event in data:
                results.append(
                    SportsOdds(
                        sport=event.get("sport_key", ""),
                        event=f"{event.get('home_team', '')} vs {event.get('away_team', '')}",
                        commence_time=event.get("commence_time", ""),
                        home_team=event.get("home_team", ""),
                        away_team=event.get("away_team", ""),
                        bookmaker_odds=event.get("bookmakers", []),
                    )
                )
            return results
        except Exception as exc:
            logger.warning("odds_api_error", error=str(exc))
            return []
