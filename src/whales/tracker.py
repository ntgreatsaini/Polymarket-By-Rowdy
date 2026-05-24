"""Whale tracking system for monitoring large Polymarket trades."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings
from src.database.models import WhaleTrade, WhaleWallet
from src.polymarket.client import PolymarketClient

logger = structlog.get_logger(__name__)


@dataclass
class WhaleAlert:
    wallet_address: str
    wallet_label: Optional[str]
    market_id: str
    market_question: str
    side: str  # BUY / SELL
    amount: float
    price: float
    smart_money_score: float
    alert_type: str  # large_buy, large_sell, conviction_shift, unusual_position
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WhaleActivity:
    total_whale_volume: float
    whale_trade_count: int
    whale_bias: str  # bullish, bearish, neutral
    net_whale_flow: float
    top_trades: list[WhaleAlert]
    smart_money_direction: str


class WhaleTracker:
    """Track and analyze whale activity on Polymarket."""

    def __init__(self, polymarket_client: PolymarketClient) -> None:
        self._poly = polymarket_client
        self._settings = get_settings()
        self._min_trade_size = self._settings.whale_min_trade_size
        self._known_wallets: dict[str, float] = {}

    async def scan_for_whale_trades(
        self,
        market_id: Optional[str] = None,
    ) -> list[WhaleAlert]:
        """Scan recent trades for whale activity."""
        try:
            trades = await self._poly.get_last_trades(market_id=market_id, limit=50)
        except Exception as exc:
            logger.warning("whale_scan_error", error=str(exc))
            return []

        alerts: list[WhaleAlert] = []
        for trade in trades:
            amount = float(trade.get("size", 0) or trade.get("amount", 0) or 0)
            price = float(trade.get("price", 0) or 0)
            value = amount * price if price > 0 else amount

            if value < self._min_trade_size:
                continue

            maker = trade.get("maker_address") or trade.get("maker", "")
            taker = trade.get("taker_address") or trade.get("taker", "")
            address = maker or taker or "unknown"
            side_raw = trade.get("side", "").upper()
            side = "BUY" if side_raw in ("BUY", "B", "0") else "SELL"

            alert_type = "large_buy" if side == "BUY" else "large_sell"
            if value > self._min_trade_size * 5:
                alert_type = f"major_{alert_type}"

            smart_score = self._known_wallets.get(address, 0.5)

            ts = datetime.now(timezone.utc)
            ts_raw = trade.get("timestamp") or trade.get("created_at")
            if ts_raw:
                try:
                    if isinstance(ts_raw, (int, float)):
                        ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                    else:
                        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                except (ValueError, TypeError, OSError):
                    pass

            market_question = trade.get("market", {}).get("question", "") if isinstance(trade.get("market"), dict) else ""
            condition_id = (
                trade.get("market", {}).get("conditionId", market_id or "")
                if isinstance(trade.get("market"), dict)
                else (market_id or trade.get("asset_id", ""))
            )

            alerts.append(
                WhaleAlert(
                    wallet_address=address,
                    wallet_label=None,
                    market_id=condition_id,
                    market_question=market_question,
                    side=side,
                    amount=value,
                    price=price,
                    smart_money_score=smart_score,
                    alert_type=alert_type,
                    timestamp=ts,
                )
            )

        logger.info("whale_scan_complete", alerts=len(alerts))
        return alerts

    def analyze_whale_activity(self, alerts: list[WhaleAlert]) -> WhaleActivity:
        """Aggregate whale alerts into activity summary."""
        if not alerts:
            return WhaleActivity(
                total_whale_volume=0,
                whale_trade_count=0,
                whale_bias="neutral",
                net_whale_flow=0,
                top_trades=[],
                smart_money_direction="neutral",
            )

        total_volume = sum(a.amount for a in alerts)
        buy_volume = sum(a.amount for a in alerts if a.side == "BUY")
        sell_volume = sum(a.amount for a in alerts if a.side == "SELL")
        net_flow = buy_volume - sell_volume

        if buy_volume > sell_volume * 1.3:
            bias = "bullish"
        elif sell_volume > buy_volume * 1.3:
            bias = "bearish"
        else:
            bias = "neutral"

        smart_buy = sum(a.amount for a in alerts if a.side == "BUY" and a.smart_money_score > 0.6)
        smart_sell = sum(a.amount for a in alerts if a.side == "SELL" and a.smart_money_score > 0.6)
        if smart_buy > smart_sell * 1.2:
            smart_dir = "bullish"
        elif smart_sell > smart_buy * 1.2:
            smart_dir = "bearish"
        else:
            smart_dir = "neutral"

        top_trades = sorted(alerts, key=lambda a: a.amount, reverse=True)[:5]

        return WhaleActivity(
            total_whale_volume=round(total_volume, 2),
            whale_trade_count=len(alerts),
            whale_bias=bias,
            net_whale_flow=round(net_flow, 2),
            top_trades=top_trades,
            smart_money_direction=smart_dir,
        )

    async def save_whale_trade(
        self, db: AsyncSession, alert: WhaleAlert
    ) -> None:
        """Persist a whale trade to the database."""
        result = await db.execute(
            select(WhaleWallet).where(WhaleWallet.address == alert.wallet_address)
        )
        wallet = result.scalar_one_or_none()

        if wallet is None:
            wallet = WhaleWallet(
                address=alert.wallet_address,
                label=alert.wallet_label,
                smart_money_score=alert.smart_money_score,
                total_trades=1,
                last_active=alert.timestamp,
            )
            db.add(wallet)
            await db.flush()
        else:
            wallet.total_trades += 1
            wallet.last_active = alert.timestamp

        trade = WhaleTrade(
            wallet_id=wallet.id,
            market_condition_id=alert.market_id,
            side=alert.side,
            amount=alert.amount,
            price=alert.price,
            timestamp=alert.timestamp,
        )
        db.add(trade)

    def register_wallet(self, address: str, smart_money_score: float) -> None:
        """Register a known wallet with a smart-money score."""
        self._known_wallets[address] = max(0, min(1, smart_money_score))
