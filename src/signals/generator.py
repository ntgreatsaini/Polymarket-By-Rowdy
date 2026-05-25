"""Enhanced signal generation engine — multi-AI consensus, momentum, order book analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from src.ai.calibration import CalibrationEngine
from src.ai.multi_ai_engine import ConsensusResult, MultiAIEngine
from src.ai.probability_engine import AIProbabilityEngine
from src.config.settings import get_settings
from src.polymarket.client import PolymarketClient
from src.polymarket.momentum import MomentumTracker
from src.sentiment.analyzer import SentimentAnalyzer, SentimentResult
from src.sentiment.enhanced_sources import EnhancedDataSources
from src.sentiment.news_fetcher import NewsFetcher
from src.whales.merlin_tracker import MerlinTracker
from src.whales.oddpool_tracker import OddPoolTracker
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
    trade_url: str = ""
    win_probability: float = 0.0  # probability of winning this trade (0-1)
    expected_value: float = 0.0  # EV in percentage
    kelly_bet_size: float = 0.0  # recommended fraction of bankroll
    risk_score_breakdown: dict[str, Any] = field(default_factory=dict)
    market_slug: str = ""
    ai_models_used: int = 1
    ai_models_agree: bool = True
    momentum_trend: str = "neutral"
    order_book_health: str = "unknown"
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
        multi_ai_engine: Optional[MultiAIEngine] = None,
        momentum_tracker: Optional[MomentumTracker] = None,
        enhanced_sources: Optional[EnhancedDataSources] = None,
        oddpool_tracker: Optional[OddPoolTracker] = None,
        merlin_tracker: Optional[MerlinTracker] = None,
    ) -> None:
        self._poly = polymarket_client
        self._ai = ai_engine
        self._news = news_fetcher
        self._sentiment = sentiment_analyzer
        self._whales = whale_tracker
        self._calibration = calibration_engine or CalibrationEngine()
        self._multi_ai = multi_ai_engine
        self._momentum = momentum_tracker or MomentumTracker(polymarket_client)
        self._enhanced = enhanced_sources or EnhancedDataSources()
        self._oddpool = oddpool_tracker or OddPoolTracker()
        self._merlin = merlin_tracker or MerlinTracker()
        self._settings = get_settings()
        self._recent_signals: set[str] = set()

    async def scan_and_generate(
        self,
        max_markets: int = 50,
        min_confidence: Optional[int] = None,
    ) -> list[TradeSignal]:
        """Scan active markets and generate signals for high-EV opportunities."""
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
        """Full enhanced analysis pipeline for a single market."""
        question = market["question"]
        category = market["category"]
        yes_price = market["yes_price"]
        no_price = market["no_price"]
        volume = market["volume"]
        liquidity = market["liquidity"]
        condition_id = market["condition_id"]

        # --- 1. Fetch news ---
        news_articles = await self._news.fetch_all(question, max_per_source=5)
        news_context = self._news.build_news_context(news_articles)

        # --- 2. Sentiment analysis (VADER + TextBlob ensemble) ---
        news_texts = [a.title + " " + a.summary for a in news_articles if a.title]
        sentiment_result = self._sentiment.analyze_texts(news_texts, source="news")

        # --- 3. Whale tracking (Polymarket CLOB + OddPool + Merlin) ---
        whale_alerts = await self._whales.scan_for_whale_trades(market_id=condition_id)
        whale_activity = self._whales.analyze_whale_activity(whale_alerts)

        # OddPool whale data (cross-venue)
        oddpool_stats = await self._oddpool.get_whale_feed(
            limit=10, platform="polymarket", min_size=self._settings.whale_min_trade_size
        )

        # Merlin smart money signal
        merlin_data = await self._merlin.get_smart_money_signal(category=category.upper())

        # --- 4. Momentum tracking ---
        momentum = self._momentum.get_momentum(condition_id, yes_price)

        # --- 5. Build context dicts ---
        sentiment_dict: dict[str, Any] = {
            "score": sentiment_result.score,
            "direction": sentiment_result.direction,
            "momentum": sentiment_result.momentum,
            "num_sources": len(sentiment_result.sources),
        }
        # Combine whale data from all sources
        combined_whale_volume = (
            whale_activity.total_whale_volume + oddpool_stats.total_volume_24h
        )
        combined_whale_count = (
            whale_activity.whale_trade_count + oddpool_stats.total_trades_24h
        )
        # Determine smart money direction considering Merlin insiders
        smart_dir = whale_activity.smart_money_direction if hasattr(whale_activity, "smart_money_direction") else whale_activity.whale_bias
        if merlin_data.smart_money_bias != "neutral":
            smart_dir = merlin_data.smart_money_bias

        whale_dict: dict[str, Any] = {
            "total_whale_volume": combined_whale_volume,
            "whale_bias": whale_activity.whale_bias,
            "whale_trade_count": combined_whale_count,
            "smart_money_direction": smart_dir,
            "oddpool_volume_24h": oddpool_stats.total_volume_24h,
            "merlin_smart_bias": merlin_data.smart_money_bias,
            "merlin_confidence": merlin_data.smart_money_confidence,
        }
        momentum_dict: dict[str, Any] = {
            "change_1h": momentum.change_1h,
            "change_6h": momentum.change_6h,
            "change_24h": momentum.change_24h,
            "trend": momentum.trend,
            "volatility": momentum.volatility,
        }

        # --- 6. AI Probability Estimation (Multi-AI or single) ---
        consensus: Optional[ConsensusResult] = None
        if self._multi_ai:
            consensus = await self._multi_ai.consensus_estimate(
                market_question=question,
                current_yes_price=yes_price,
                current_no_price=no_price,
                volume=volume,
                liquidity=liquidity,
                news_context=news_context,
                sentiment_data=sentiment_dict,
                whale_data=whale_dict,
                category=category,
                momentum_data=momentum_dict,
            )
            ai_prob_raw = consensus.probability
            ai_confidence = consensus.confidence
            ai_reasoning = consensus.reasoning
            ai_risk = consensus.risk_level
            ai_factors = consensus.factors
            models_used = consensus.num_models_used
            models_agree = consensus.models_agree
        else:
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
            ai_prob_raw = estimate.ai_probability
            ai_confidence = estimate.confidence_score
            ai_reasoning = estimate.reasoning
            ai_risk = estimate.risk_level
            ai_factors = estimate.factors
            models_used = 1
            models_agree = True

        # --- 7. Bayesian calibration ---
        calibrated = self._calibration.bayesian_adjust(
            ai_probability=ai_prob_raw,
            market_probability=yes_price,
            confidence=ai_confidence,
            category=category,
        )

        ai_prob = calibrated.adjusted_probability
        edge = round((ai_prob - yes_price) * 100, 2)

        # --- 8. Enhanced filtering ---
        if abs(edge) < 5:
            return None

        # Require AI-sentiment alignment for higher confidence
        sentiment_agrees = self._check_sentiment_alignment(
            edge, sentiment_result, whale_activity
        )
        if not sentiment_agrees and abs(edge) < 10:
            ai_confidence = max(20, ai_confidence - 15)

        # Penalize when multi-AI models disagree
        if not models_agree:
            ai_confidence = max(15, ai_confidence - 10)

        direction = "YES" if edge > 0 else "NO"
        if direction == "NO":
            ai_prob = 1 - ai_prob
            edge = round((ai_prob - no_price) * 100, 2)

        # --- 9. Risk assessment ---
        risk = self._assess_risk(ai_confidence, ai_risk, liquidity, volume, whale_activity, momentum)
        liq_rating = self._rate_liquidity(liquidity)
        vol_rating = self._rate_volatility(yes_price, volume)

        entry_price = yes_price if direction == "YES" else no_price
        suggested_entry = f"Below {entry_price + 0.05:.0%}" if direction == "YES" else f"Below {no_price + 0.05:.0%}"
        suggested_exit = f"Above {ai_prob:.0%}"
        time_horizon = self._estimate_time_horizon(market)

        news_summary = self._summarize_news(news_articles)
        sentiment_summary = self._summarize_sentiment(sentiment_result)
        whale_summary = self._summarize_whales_enhanced(
            whale_activity, oddpool_stats, merlin_data
        )

        # --- 10. Win probability, EV, Kelly ---
        win_prob = ai_prob
        trade_price = yes_price if direction == "YES" else no_price
        ev = self._calibration.calculate_expected_value(win_prob, trade_price, ai_confidence)
        kelly = self._calibration.kelly_criterion(win_prob, trade_price, fraction=0.25)

        # --- 11. Trade URL ---
        slug = market.get("slug", "")
        trade_url = f"https://polymarket.com/event/{slug}" if slug else ""

        # --- 12. Risk score breakdown ---
        risk_breakdown = self._build_risk_breakdown(
            ai_confidence, ai_risk, liquidity, volume, whale_activity, momentum,
            sentiment_result, models_agree, ev,
        )

        return TradeSignal(
            market_title=question,
            condition_id=condition_id,
            category=category,
            yes_probability=yes_price,
            no_probability=no_price,
            ai_probability=ai_prob,
            expected_edge=edge,
            confidence_score=ai_confidence,
            liquidity_rating=liq_rating,
            volatility_rating=vol_rating,
            risk_level=risk,
            ai_reasoning=ai_reasoning,
            news_summary=news_summary,
            sentiment_summary=sentiment_summary,
            whale_summary=whale_summary,
            suggested_entry=suggested_entry,
            suggested_exit=suggested_exit,
            time_horizon=time_horizon,
            direction=direction,
            trade_url=trade_url,
            win_probability=round(win_prob, 4),
            expected_value=ev,
            kelly_bet_size=kelly,
            risk_score_breakdown=risk_breakdown,
            market_slug=slug,
            ai_models_used=models_used,
            ai_models_agree=models_agree,
            momentum_trend=momentum.trend,
            order_book_health="unknown",
        )

    @staticmethod
    def _check_sentiment_alignment(
        edge: float,
        sentiment: SentimentResult,
        whale_activity: WhaleActivity,
    ) -> bool:
        """Check if sentiment and whale data align with the AI edge direction."""
        bullish_edge = edge > 0
        sentiment_bullish = sentiment.direction == "bullish"
        sentiment_bearish = sentiment.direction == "bearish"
        whale_bullish = whale_activity.whale_bias in ("bullish", "neutral")

        if bullish_edge:
            return sentiment_bullish or (not sentiment_bearish and whale_bullish)
        else:
            return sentiment_bearish or (not sentiment_bullish and not whale_bullish)

    @staticmethod
    def _assess_risk(
        confidence: int,
        ai_risk: str,
        liquidity: float,
        volume: float,
        whale_activity: WhaleActivity,
        momentum: Any,
    ) -> str:
        risk_score = 0

        if confidence < 40:
            risk_score += 3
        elif confidence < 60:
            risk_score += 2
        elif confidence < 75:
            risk_score += 1

        if ai_risk == "very_high":
            risk_score += 2
        elif ai_risk == "high":
            risk_score += 1

        if liquidity < 10_000:
            risk_score += 2
        elif liquidity < 50_000:
            risk_score += 1

        if volume < 5_000:
            risk_score += 1

        if whale_activity.whale_bias == "bearish" and whale_activity.total_whale_volume > 5000:
            risk_score += 1

        if hasattr(momentum, "volatility") and momentum.volatility == "high":
            risk_score += 1

        if risk_score >= 6:
            return "very_high"
        elif risk_score >= 4:
            return "high"
        elif risk_score >= 2:
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
        agreement = ""
        if result.details.get("vader_textblob_agree"):
            agreement = " [VADER+TextBlob agree]"
        return f"{emoji} {result.direction.title()} (score: {result.score:+.2f}, samples: {result.sample_size}){agreement}"

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

    def _summarize_whales_enhanced(self, activity: WhaleActivity, oddpool_stats: Any, merlin_data: Any) -> str:
        """Enhanced whale summary combining Polymarket CLOB + OddPool + Merlin data."""
        parts: list[str] = []

        # Base CLOB data
        if activity.whale_trade_count > 0:
            top = activity.top_trades[0] if activity.top_trades else None
            top_str = f"\nTop: ${top.amount:,.0f} {top.side}" if top else ""
            parts.append(
                f"🐋 {activity.whale_trade_count} whale trades, "
                f"${activity.total_whale_volume:,.0f} total, "
                f"bias: {activity.whale_bias}{top_str}"
            )

        # OddPool cross-venue data
        if oddpool_stats.total_volume_24h > 0:
            oddpool_summary = self._oddpool.format_whale_summary(oddpool_stats)
            if oddpool_summary:
                parts.append(oddpool_summary)

        # Merlin smart money
        if merlin_data.top_traders:
            merlin_summary = self._merlin.format_smart_money_summary(merlin_data)
            if merlin_summary:
                parts.append(merlin_summary)

        if not parts:
            return "No significant whale activity"
        return "\n".join(parts)

    @staticmethod
    def _build_risk_breakdown(
        confidence: int,
        ai_risk: str,
        liquidity: float,
        volume: float,
        whale_activity: WhaleActivity,
        momentum: Any,
        sentiment: SentimentResult,
        models_agree: bool,
        ev: float,
    ) -> dict[str, Any]:
        """Build a detailed risk breakdown for the signal."""
        factors: dict[str, Any] = {}
        factors["confidence_level"] = (
            "Strong" if confidence >= 75 else "Moderate" if confidence >= 55 else "Weak"
        )
        factors["ai_risk_assessment"] = ai_risk.replace("_", " ").title()
        factors["liquidity_risk"] = (
            "Low" if liquidity >= 50_000 else "Medium" if liquidity >= 10_000 else "High"
        )
        factors["volume_risk"] = (
            "Low" if volume >= 50_000 else "Medium" if volume >= 10_000 else "High"
        )
        factors["whale_alignment"] = whale_activity.whale_bias.title()
        factors["sentiment_direction"] = sentiment.direction.title()
        factors["ai_consensus"] = "Aligned" if models_agree else "Split"
        factors["momentum"] = (
            momentum.trend.title() if hasattr(momentum, "trend") else "N/A"
        )
        factors["volatility"] = (
            momentum.volatility.title() if hasattr(momentum, "volatility") else "N/A"
        )
        factors["ev_positive"] = ev > 0
        return factors

    def clear_recent_signals(self) -> None:
        """Clear the deduplication cache."""
        self._recent_signals.clear()
