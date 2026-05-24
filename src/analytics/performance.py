"""Performance tracking and analytics engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    Market,
    PerformanceMetric,
    Signal,
    SignalStatus,
)

logger = structlog.get_logger(__name__)


class PerformanceTracker:
    """Track and calculate bot performance metrics."""

    async def calculate_metrics(
        self,
        db: AsyncSession,
        period: str = "all_time",
    ) -> dict[str, Any]:
        """Calculate performance metrics for a given period."""
        query = select(Signal)

        if period == "weekly":
            since = datetime.now(timezone.utc) - timedelta(days=7)
            query = query.where(Signal.created_at >= since)
        elif period == "monthly":
            since = datetime.now(timezone.utc) - timedelta(days=30)
            query = query.where(Signal.created_at >= since)

        result = await db.execute(query)
        signals = result.scalars().all()

        total = len(signals)
        resolved = [s for s in signals if s.status in (SignalStatus.RESOLVED_WIN, SignalStatus.RESOLVED_LOSS)]
        wins = sum(1 for s in resolved if s.status == SignalStatus.RESOLVED_WIN)
        losses = sum(1 for s in resolved if s.status == SignalStatus.RESOLVED_LOSS)

        win_rate = wins / len(resolved) if resolved else 0.0
        total_roi = sum(s.profit_loss or 0 for s in resolved)
        avg_confidence = sum(s.confidence_score for s in signals) / total if total else 0

        category_stats = self._calculate_category_stats(resolved)

        return {
            "period": period,
            "total_signals": total,
            "resolved": len(resolved),
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_roi": total_roi,
            "avg_confidence": avg_confidence,
            "best_category": category_stats.get("best", "N/A"),
            "worst_category": category_stats.get("worst", "N/A"),
            "category_breakdown": category_stats.get("breakdown", {}),
        }

    async def resolve_signal(
        self,
        db: AsyncSession,
        signal_id: int,
        outcome: str,
    ) -> Optional[Signal]:
        """Resolve a signal as win or loss based on market outcome."""
        result = await db.execute(select(Signal).where(Signal.id == signal_id))
        signal = result.scalar_one_or_none()
        if not signal:
            return None

        if outcome.upper() == signal.direction.value:
            signal.status = SignalStatus.RESOLVED_WIN
            signal.profit_loss = abs(signal.expected_edge) / 100.0
        else:
            signal.status = SignalStatus.RESOLVED_LOSS
            signal.profit_loss = -(signal.market_probability)

        signal.resolved_at = datetime.now(timezone.utc)
        await db.flush()

        logger.info(
            "signal_resolved",
            signal_id=signal_id,
            status=signal.status.value,
            pnl=signal.profit_loss,
        )
        return signal

    async def auto_resolve_markets(self, db: AsyncSession) -> int:
        """Auto-resolve signals for markets that have ended."""
        result = await db.execute(
            select(Signal)
            .join(Market)
            .where(
                Signal.status == SignalStatus.ACTIVE,
                Market.outcome.isnot(None),
            )
        )
        signals = result.scalars().all()
        resolved_count = 0

        for signal in signals:
            market_result = await db.execute(
                select(Market).where(Market.id == signal.market_id)
            )
            market = market_result.scalar_one_or_none()
            if market and market.outcome:
                await self.resolve_signal(db, signal.id, market.outcome)
                resolved_count += 1

        logger.info("auto_resolved", count=resolved_count)
        return resolved_count

    async def save_metrics(
        self,
        db: AsyncSession,
        metrics: dict[str, Any],
    ) -> None:
        """Persist performance metrics to the database."""
        pm = PerformanceMetric(
            period=metrics["period"],
            period_start=datetime.now(timezone.utc),
            total_signals=metrics["total_signals"],
            winning_signals=metrics["wins"],
            losing_signals=metrics["losses"],
            win_rate=metrics["win_rate"],
            total_roi=metrics["total_roi"],
            avg_confidence=metrics["avg_confidence"],
            best_category=metrics.get("best_category"),
            worst_category=metrics.get("worst_category"),
        )
        db.add(pm)

    @staticmethod
    def _calculate_category_stats(
        resolved_signals: list[Signal],
    ) -> dict[str, Any]:
        """Calculate per-category win rates."""
        categories: dict[str, dict[str, int]] = {}

        for s in resolved_signals:
            market_result = s.market
            cat = "other"
            if hasattr(market_result, "category"):
                cat = market_result.category.value if hasattr(market_result.category, "value") else str(market_result.category)

            if cat not in categories:
                categories[cat] = {"wins": 0, "total": 0}
            categories[cat]["total"] += 1
            if s.status == SignalStatus.RESOLVED_WIN:
                categories[cat]["wins"] += 1

        breakdown: dict[str, float] = {}
        best = ("N/A", 0.0)
        worst = ("N/A", 1.0)

        for cat, stats in categories.items():
            wr = stats["wins"] / stats["total"] if stats["total"] else 0
            breakdown[cat] = wr
            if stats["total"] >= 3:
                if wr > best[1]:
                    best = (cat, wr)
                if wr < worst[1]:
                    worst = (cat, wr)

        return {
            "best": best[0],
            "worst": worst[0],
            "breakdown": breakdown,
        }
