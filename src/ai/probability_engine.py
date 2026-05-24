"""AI probability estimation engine using OpenAI and multi-factor analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog
from openai import AsyncOpenAI

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class ProbabilityEstimate:
    ai_probability: float
    confidence_score: int
    reasoning: str
    factors: dict[str, Any] = field(default_factory=dict)
    edge: float = 0.0
    risk_level: str = "medium"


class AIProbabilityEngine:
    """Multi-factor AI reasoning engine for market probability estimation."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    async def estimate_probability(
        self,
        market_question: str,
        current_yes_price: float,
        current_no_price: float,
        volume: float,
        liquidity: float,
        news_context: Optional[str] = None,
        sentiment_data: Optional[dict[str, Any]] = None,
        whale_data: Optional[dict[str, Any]] = None,
        category: str = "other",
    ) -> ProbabilityEstimate:
        """Estimate the true probability of a market event using AI reasoning."""
        prompt = self._build_prompt(
            market_question=market_question,
            current_yes_price=current_yes_price,
            current_no_price=current_no_price,
            volume=volume,
            liquidity=liquidity,
            news_context=news_context,
            sentiment_data=sentiment_data,
            whale_data=whale_data,
            category=category,
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content or "{}"
            result = json.loads(content)

            ai_prob = float(result.get("probability", 50)) / 100.0
            ai_prob = max(0.01, min(0.99, ai_prob))
            confidence = int(result.get("confidence", 50))
            confidence = max(0, min(100, confidence))
            reasoning = result.get("reasoning", "No reasoning provided.")
            risk = result.get("risk_level", "medium").lower()
            factors = result.get("factors", {})

            market_prob = current_yes_price
            edge = round((ai_prob - market_prob) * 100, 2)

            return ProbabilityEstimate(
                ai_probability=round(ai_prob, 4),
                confidence_score=confidence,
                reasoning=reasoning,
                factors=factors,
                edge=edge,
                risk_level=risk if risk in ("low", "medium", "high", "very_high") else "medium",
            )

        except Exception as exc:
            logger.error("ai_estimation_failed", error=str(exc), market=market_question)
            return ProbabilityEstimate(
                ai_probability=current_yes_price,
                confidence_score=20,
                reasoning=f"AI estimation failed: {str(exc)[:200]}",
                edge=0.0,
                risk_level="high",
            )

    def _system_prompt(self) -> str:
        return """You are an expert prediction market analyst and probability estimator. Your job is to estimate the TRUE probability of events traded on Polymarket.

You must:
1. Analyze all available information objectively
2. Consider base rates and reference classes
3. Account for uncertainty
4. Avoid overconfidence
5. Consider multiple scenarios
6. Weight recent information appropriately
7. Identify potential market inefficiencies

CRITICAL RULES:
- Never give 0% or 100% probability unless the event is physically impossible or already happened
- Be calibrated: events you rate at 70% should happen ~70% of the time
- Account for unknown unknowns by hedging toward 50%
- Consider market manipulation and wash trading
- If you lack information, express that through lower confidence, not extreme probabilities

Respond ONLY in JSON format with these fields:
{
  "probability": <number 1-99, your estimated probability as a percentage>,
  "confidence": <number 0-100, how confident you are in your estimate>,
  "reasoning": "<string, 2-4 bullet points explaining your reasoning>",
  "risk_level": "<low|medium|high|very_high>",
  "factors": {
    "news_impact": "<positive|negative|neutral>",
    "sentiment_alignment": <true|false>,
    "momentum": "<bullish|bearish|neutral>",
    "key_risk": "<string, main risk factor>"
  }
}"""

    def _build_prompt(
        self,
        market_question: str,
        current_yes_price: float,
        current_no_price: float,
        volume: float,
        liquidity: float,
        news_context: Optional[str],
        sentiment_data: Optional[dict[str, Any]],
        whale_data: Optional[dict[str, Any]],
        category: str,
    ) -> str:
        parts = [
            "## Market Analysis Request",
            f"**Question:** {market_question}",
            f"**Category:** {category}",
            f"**Current YES Price:** {current_yes_price:.2%}",
            f"**Current NO Price:** {current_no_price:.2%}",
            f"**Volume:** ${volume:,.0f}",
            f"**Liquidity:** ${liquidity:,.0f}",
        ]

        if news_context:
            parts.append(f"\n## Recent News\n{news_context}")

        if sentiment_data:
            score = sentiment_data.get("score", 0)
            direction = sentiment_data.get("direction", "neutral")
            momentum = sentiment_data.get("momentum", 0)
            parts.append(
                f"\n## Sentiment Analysis\n"
                f"- Score: {score:.2f} (-1 bearish to +1 bullish)\n"
                f"- Direction: {direction}\n"
                f"- Momentum: {momentum:.2f}"
            )

        if whale_data:
            total = whale_data.get("total_whale_volume", 0)
            bias = whale_data.get("whale_bias", "neutral")
            count = whale_data.get("whale_trade_count", 0)
            parts.append(
                f"\n## Whale Activity\n"
                f"- Total whale volume: ${total:,.0f}\n"
                f"- Whale bias: {bias}\n"
                f"- Recent whale trades: {count}"
            )

        parts.append(
            "\nEstimate the TRUE probability of YES for this market. "
            "Consider all factors above and provide your analysis."
        )

        return "\n".join(parts)

    async def batch_estimate(
        self,
        markets: list[dict[str, Any]],
    ) -> list[ProbabilityEstimate]:
        """Estimate probabilities for multiple markets."""
        results: list[ProbabilityEstimate] = []
        for m in markets:
            estimate = await self.estimate_probability(
                market_question=m.get("question", ""),
                current_yes_price=m.get("yes_price", 0.5),
                current_no_price=m.get("no_price", 0.5),
                volume=m.get("volume", 0),
                liquidity=m.get("liquidity", 0),
                news_context=m.get("news_context"),
                sentiment_data=m.get("sentiment_data"),
                whale_data=m.get("whale_data"),
                category=m.get("category", "other"),
            )
            results.append(estimate)
        return results
