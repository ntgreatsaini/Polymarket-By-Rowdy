"""FastAPI routes for admin dashboard and health monitoring."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter
from sqlalchemy import func, select

from src.database.models import Market, Signal, SignalStatus, WhaleWallet
from src.database.session import get_db

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "polymarket-bot"}


@router.get("/api/v1/markets")
async def list_markets(
    limit: int = 20,
    offset: int = 0,
    category: str | None = None,
) -> dict[str, Any]:
    async with get_db() as db:
        query = select(Market).where(Market.is_active.is_(True))
        if category:
            query = query.where(Market.category == category)
        query = query.order_by(Market.volume.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        markets = result.scalars().all()

        return {
            "count": len(markets),
            "markets": [
                {
                    "id": m.id,
                    "condition_id": m.condition_id,
                    "question": m.question,
                    "category": m.category.value if hasattr(m.category, "value") else m.category,
                    "yes_price": m.yes_price,
                    "no_price": m.no_price,
                    "volume": m.volume,
                    "liquidity": m.liquidity,
                }
                for m in markets
            ],
        }


@router.get("/api/v1/signals")
async def list_signals(
    limit: int = 20,
    status: str = "active",
) -> dict[str, Any]:
    async with get_db() as db:
        query = select(Signal)
        if status == "active":
            query = query.where(Signal.status == SignalStatus.ACTIVE)
        query = query.order_by(Signal.confidence_score.desc()).limit(limit)
        result = await db.execute(query)
        signals = result.scalars().all()

        return {
            "count": len(signals),
            "signals": [
                {
                    "id": s.id,
                    "market_id": s.market_id,
                    "direction": s.direction.value,
                    "ai_probability": s.ai_probability,
                    "expected_edge": s.expected_edge,
                    "confidence_score": s.confidence_score,
                    "risk_level": s.risk_level.value if hasattr(s.risk_level, "value") else s.risk_level,
                    "status": s.status.value,
                    "created_at": s.created_at.isoformat(),
                }
                for s in signals
            ],
        }


@router.get("/api/v1/performance")
async def get_performance() -> dict[str, Any]:
    async with get_db() as db:
        total_q = select(func.count(Signal.id))
        total_result = await db.execute(total_q)
        total = total_result.scalar() or 0

        wins_q = select(func.count(Signal.id)).where(
            Signal.status == SignalStatus.RESOLVED_WIN
        )
        wins_result = await db.execute(wins_q)
        wins = wins_result.scalar() or 0

        losses_q = select(func.count(Signal.id)).where(
            Signal.status == SignalStatus.RESOLVED_LOSS
        )
        losses_result = await db.execute(losses_q)
        losses = losses_result.scalar() or 0

        resolved = wins + losses
        win_rate = wins / resolved if resolved > 0 else 0

        return {
            "total_signals": total,
            "resolved": resolved,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 4),
        }


@router.get("/api/v1/whales")
async def list_whales(limit: int = 20) -> dict[str, Any]:
    async with get_db() as db:
        query = (
            select(WhaleWallet)
            .where(WhaleWallet.is_tracked.is_(True))
            .order_by(WhaleWallet.smart_money_score.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        wallets = result.scalars().all()

        return {
            "count": len(wallets),
            "whales": [
                {
                    "id": w.id,
                    "address": w.address[:10] + "..." + w.address[-6:] if len(w.address) > 16 else w.address,
                    "label": w.label,
                    "smart_money_score": w.smart_money_score,
                    "total_trades": w.total_trades,
                    "total_profit": w.total_profit,
                    "win_rate": w.win_rate,
                }
                for w in wallets
            ],
        }


@router.post("/api/v1/admin/broadcast")
async def admin_broadcast(message: str) -> dict[str, str]:
    return {"status": "ok", "detail": "Broadcast queued"}


@router.get("/api/v1/admin/stats")
async def admin_stats() -> dict[str, Any]:
    async with get_db() as db:
        markets_count = await db.execute(
            select(func.count(Market.id)).where(Market.is_active.is_(True))
        )
        signals_count = await db.execute(
            select(func.count(Signal.id)).where(Signal.status == SignalStatus.ACTIVE)
        )
        whales_count = await db.execute(
            select(func.count(WhaleWallet.id)).where(WhaleWallet.is_tracked.is_(True))
        )

        return {
            "active_markets": markets_count.scalar() or 0,
            "active_signals": signals_count.scalar() or 0,
            "tracked_whales": whales_count.scalar() or 0,
        }
