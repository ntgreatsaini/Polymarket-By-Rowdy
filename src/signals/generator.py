"""Signal generation engine combining all analysis components."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from src.ai.calibration import CalibrationEngine
from src.ai.probability_engine import AIProbabilityEngine, ProbabilityEstimate
from src.config.settings import get_settings
from src.polymarket.client import PolymarketClient
from src.sentiment.analyzer import SentimentAnalyzer, SentimentResult
from src.sentiment.news_fetcher import NewsFetcher
from src.whales.tracker import WhaleActivity, WhaleTracker

logger = structlog.get_logger(__name__)


@dataclass
class TradeSignal:
    market_title: str
    condition_id: str
    category: str
    yes_probability: float
    no_probability: float
    ai_probability: float
    expected_edge: float
    confidence_score: int
    liquidity_rating: str
    volatility_rating: str
    risk_level: str
    ai_reasoning: str
    news_summary: str
    sentiment_summary: str
    whale_summary: str
    suggested_entry: str
    suggested_exit: str
    time_horizon: str
    direction: str  # YES or NO
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SignalGenerator:
    """Orchestrates all analysis components to produce high-quality trade signals."""

    def __init__(
        self,
        polymarket_client: PolymarketClient,
        ai_engine: AIProbabilityEngine,
        news_fetcher: NewsFetcher,
        sentiment_analyzer: SentimentAnalyzer,
        whale_tracker: WhaleTracker,
        calibration_engine: Optional[CalibrationEngine] = None,
    ) -> None:
        self._poly = polymarket_client
        self._ai = ai_engine
        self._news = news_fetcher
        self._sentiment = sentiment_analyzer
        self._whales = whale_tracker
        self._calibration = calibration_engine or CalibrationEngine()
        self._settings = get_settings()
        self._recent_signals: set[str] = set()

    async def scan_and_generate(
        self,
        max_markets: int = 50,
        min_confidence: Optional[int] = None,
    ) -> list[TradeSignal]:
        """Scan all active markets and generate signals for high-EV opportunities."""
        if min_confidence is None:
            min_confidence = self._settings.signal_min_confidence

        raw_markets = await self._poly.get_all_active_markets(max_pages=5)
        parsed = [self._poly.parse_market(m) for m in raw_markets]

        filtered = [
            m for m in parsed
            if m["liquidity"] >= self._settings.signal_min_liquidity
            and m["is_active"]
            and 0.05 <= m["yes_price"] <= 0.95
        ]

        filtered.sort(key=lambda m: m["volume"], reverse=True)
        filtered = filtered[:max_markets]

        logger.info("signal_scan_start", total_markets=len(parsed), filtered=len(filtered))

        signals: list[TradeSignal] = []
        for market in filtered:
            cid = market["condition_id"]
            if cid in self._recent_signals:
                continue

            try:
                signal = await self._analyze_market(market)
                if signal and signal.confidence_score >= min_confidence:
                    signals.append(signal)
                    self._recent_signals.add(cid)
            except Exception as exc:
                logger.warning("market_analysis_error", market=cid, error=str(exc))

        signals.sort(key=lambda s: (s.confidence_score, abs(s.expected_edge)), reverse=True)
        logger.info("signal_scan_complete", signals_generated=len(signals))
        return signals

    async def analyze_single_market(self, query: str) -> Optional[TradeSignal]:
        """Analyze a single market by search query."""
        results = await self._poly.search_markets(query, limit=5)
        if not results:
            return None

        market = self._poly.parse_market(results[0])
        return await self._analyze_market(market)

    async def _analyze_market(self, market: dict[str, Any]) -> Optional[TradeSignal]:
        """Full analysis pipeline for a single market."""
        question = market["question"]
        category = market["category"]
        yes_price = market["yes_price"]
        no_price = market["no_price"]
        volume = market["volume"]
        liquidity = market["liquidity"]
        condition_id = market["condition_id"]

        news_articles = await self._news.fetch_all(question, max_per_source=5)
        news_context = self._news.build_news_context(news_articles)

        news_texts = [a.title + " " + a.summary for a in news_articles if a.title]
        sentiment_result = self._sentiment.analyze_texts(news_texts, source="news")

        whale_alerts = await self._whales.scan_for_whale_trades(market_id=condition_id)
        whale_activity = self._whales.analyze_whale_activity(whale_alerts)

        sentiment_dict: dict[str, Any] = {
            "score": sentiment_result.score,
            "direction": sentiment_result.direction,
            "momentum": sentiment_result.momentum,
        }
        whale_dict: dict[str, Any] = {
            "total_whale_volume": whale_activity.total_whale_volume,
            "whale_bias": whale_activity.whale_bias,
            "whale_trade_count": whale_activity.whale_trade_count,
        }

        estimate = await self._ai.estimate_probability(
            market_question=question,
            current_yes_price=yes_price,
            current_no_price=no_price,
            volume=volume,
            liquidity=liquidity,
            news_context=news_context,
            sentiment_data=sentiment_dict,
            whale_data=whale_dict,
            category=category,
        )

        calibrated = self._calibration.bayesian_adjust(
            ai_probability=estimate.ai_probability,
            market_probability=yes_price,
            confidence=estimate.confidence_score,
            category=category,
        )

        ai_prob = calibrated.adjusted_probability
        edge = round((ai_prob - yes_price) * 100, 2)

        if abs(edge) < 5:
            return None

        direction = "YES" if edge > 0 else "NO"
        if direction == "NO":
            ai_prob = 1 - ai_prob
            edge = round((ai_prob - no_price) * 100, 2)

        confidence = estimate.confidence_score
        risk = self._assess_risk(estimate, liquidity, volume, whale_activity)
        liq_rating = self._rate_liquidity(liquidity)
        vol_rating = self._rate_volatility(yes_price, volume)

        entry_price = yes_price if direction == "YES" else no_price
        suggested_entry = f"Below {entry_price + 0.05:.0%}" if direction == "YES" else f"Below {no_price + 0.05:.0%}"
        suggested_exit = f"Above {ai_prob:.0%}"
        time_horizon = self._estimate_time_horizon(market)

        news_summary = self._summarize_news(news_articles)
        sentiment_summary = self._summarize_sentiment(sentiment_result)
        whale_summary = self._summarize_whales(whale_activity)

        return TradeSignal(
            market_title=question,
            condition_id=condition_id,
            category=category,
            yes_probability=yes_price,
            no_probability=no_price,
            ai_probability=ai_prob,
            expected_edge=edge,
            confidence_score=confidence,
            liquidity_rating=liq_rating,
            volatility_rating=vol_rating,
            risk_level=risk,
            ai_reasoning=estimate.reasoning,
            news_summary=news_summary,
            sentiment_summary=sentiment_summary,
            whale_summary=whale_summary,
            suggested_entry=suggested_entry,
            suggested_exit=suggested_exit,
            time_horizon=time_horizon,
            direction=direction,
        )

    def _assess_risk(
        self,
        estimate: ProbabilityEstimate,
        liquidity: float,
        volume: float,
        whale_activity: WhaleActivity,
    ) -> str:
        risk_score = 0
        if estimate.confidence_score < 50:
            risk_score += 2
        elif estimate.confidence_score < 70:
            risk_score += 1

        if liquidity < 10_000:
            risk_score += 2
        elif liquidity < 50_000:
            risk_score += 1

        if volume < 5_000:
            risk_score += 1

        if whale_activity.whale_bias == "bearish" and whale_activity.total_whale_volume > 5000:
            risk_score += 1

        if risk_score >= 5:
            return "very_high"
        elif risk_score >= 3:
            return "high"
        elif risk_score >= 1:
            return "medium"
        return "low"

    @staticmethod
    def _rate_liquidity(liquidity: float) -> str:
        if liquidity >= 100_000:
            return "Very High"
        elif liquidity >= 50_000:
            return "High"
        elif liquidity >= 10_000:
            return "Medium"
        return "Low"

    @staticmethod
    def _rate_volatility(yes_price: float, volume: float) -> str:
        mid_distance = abs(yes_price - 0.5)
        if mid_distance < 0.1 and volume > 50_000:
            return "High"
        elif mid_distance < 0.2:
            return "Medium"
        return "Low"

    @staticmethod
    def _estimate_time_horizon(market: dict[str, Any]) -> str:
        end_date = market.get("end_date")
        if not end_date:
            return "Unknown"
        now = datetime.now(timezone.utc)
        delta = end_date - now
        days = delta.days
        if days <= 1:
            return "< 24 hours"
        elif days <= 7:
            return f"{days} days"
        elif days <= 30:
            return f"{days // 7} weeks"
        return f"{days // 30} months"

    @staticmethod
    def _summarize_news(articles: list[Any]) -> str:
        if not articles:
            return "No recent news found"
        lines = [f"• {a.title}" for a in articles[:4]]
        return "\n".join(lines)

    @staticmethod
    def _summarize_sentiment(result: SentimentResult) -> str:
        emoji = "📈" if result.direction == "bullish" else "📉" if result.direction == "bearish" else "➡️"
        return f"{emoji} {result.direction.title()} (score: {result.score:+.2f}, samples: {result.sample_size})"

    @staticmethod
    def _summarize_whales(activity: WhaleActivity) -> str:
        if activity.whale_trade_count == 0:
            return "No significant whale activity"
        top = activity.top_trades[0] if activity.top_trades else None
        top_str = f"${top.amount:,.0f} {top.side}" if top else ""
        return (
            f"🐋 {activity.whale_trade_count} whale trades, "
            f"${activity.total_whale_volume:,.0f} total, "
            f"bias: {activity.whale_bias}"
            + (f"\nTop: {top_str}" if top_str else "")
        )

    def clear_recent_signals(self) -> None:
        """Clear the deduplication cache."""
        self._recent_signals.clear()
