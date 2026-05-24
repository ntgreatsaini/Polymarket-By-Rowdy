"""SQLAlchemy ORM models for the Polymarket bot."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────


class MarketCategory(str, enum.Enum):
    CRYPTO = "crypto"
    POLITICS = "politics"
    SPORTS = "sports"
    AI_TECH = "ai_tech"
    MACRO = "macro"
    GLOBAL_EVENTS = "global_events"
    OTHER = "other"


class SignalDirection(str, enum.Enum):
    YES = "YES"
    NO = "NO"


class SignalStatus(str, enum.Enum):
    ACTIVE = "active"
    RESOLVED_WIN = "resolved_win"
    RESOLVED_LOSS = "resolved_loss"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


# ── Users ──────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")


# ── Telegram Groups ───────────────────────────────────


class TelegramGroup(Base):
    __tablename__ = "telegram_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    chat_type: Mapped[str] = mapped_column(String(50), default="group")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Markets ────────────────────────────────────────────


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    condition_id: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    category: Mapped[MarketCategory] = mapped_column(
        Enum(MarketCategory), default=MarketCategory.OTHER
    )
    yes_price: Mapped[float] = mapped_column(Float, default=0.0)
    no_price: Mapped[float] = mapped_column(Float, default=0.0)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    liquidity: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    signals: Mapped[list["Signal"]] = relationship(back_populates="market")
    snapshots: Mapped[list["MarketSnapshot"]] = relationship(back_populates="market")
    ai_predictions: Mapped[list["AIPrediction"]] = relationship(back_populates="market")

    __table_args__ = (Index("ix_markets_category_active", "category", "is_active"),)


# ── Signals ────────────────────────────────────────────


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection), nullable=False)
    market_probability: Mapped[float] = mapped_column(Float, nullable=False)
    ai_probability: Mapped[float] = mapped_column(Float, nullable=False)
    expected_edge: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.MEDIUM)
    liquidity_rating: Mapped[str] = mapped_column(String(20), default="Medium")
    volatility_rating: Mapped[str] = mapped_column(String(20), default="Medium")
    ai_reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    news_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sentiment_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    whale_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_entry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    suggested_exit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    time_horizon: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus), default=SignalStatus.ACTIVE
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    profit_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    market: Mapped["Market"] = relationship(back_populates="signals")

    __table_args__ = (
        Index("ix_signals_status_confidence", "status", "confidence_score"),
    )


# ── Signal History ─────────────────────────────────────


class SignalHistory(Base):
    __tablename__ = "signal_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), nullable=False, index=True)
    field_changed: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Whale Wallets ──────────────────────────────────────


class WhaleWallet(Base):
    __tablename__ = "whale_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_profit: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    smart_money_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=True)
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    trades: Mapped[list["WhaleTrade"]] = relationship(back_populates="wallet")


# ── Whale Trades ───────────────────────────────────────


class WhaleTrade(Base):
    __tablename__ = "whale_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("whale_wallets.id"), nullable=False, index=True
    )
    market_condition_id: Mapped[str] = mapped_column(String(512), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    wallet: Mapped["WhaleWallet"] = relationship(back_populates="trades")


# ── AI Predictions ─────────────────────────────────────


class AIPrediction(Base):
    __tablename__ = "ai_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    ai_probability: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    factors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    market: Mapped["Market"] = relationship(back_populates="ai_predictions")


# ── Sentiment Data ─────────────────────────────────────


class SentimentData(Base):
    __tablename__ = "sentiment_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_condition_id: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, index=True
    )
    topic: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    momentum_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    direction: Mapped[str] = mapped_column(String(20), default="neutral")
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Market Snapshots ───────────────────────────────────


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    yes_price: Mapped[float] = mapped_column(Float, nullable=False)
    no_price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    liquidity: Mapped[float] = mapped_column(Float, default=0.0)
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    market: Mapped["Market"] = relationship(back_populates="snapshots")


# ── Subscriptions ──────────────────────────────────────


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    category: Mapped[Optional[MarketCategory]] = mapped_column(
        Enum(MarketCategory), nullable=True
    )
    min_confidence: Mapped[int] = mapped_column(Integer, default=65)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="subscriptions")

    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_user_category"),
    )


# ── Performance Metrics ────────────────────────────────


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_signals: Mapped[int] = mapped_column(Integer, default=0)
    winning_signals: Mapped[int] = mapped_column(Integer, default=0)
    losing_signals: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    total_roi: Mapped[float] = mapped_column(Float, default=0.0)
    avg_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    best_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    worst_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── News Events ────────────────────────────────────────


class NewsEvent(Base):
    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    related_market_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("markets.id"), nullable=True
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
