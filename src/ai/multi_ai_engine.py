"""Multi-AI Consensus Engine — ensemble probability estimation across providers."""

from __future__ import annotations

import asyncio
import json
import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

ANALYSIS_SYSTEM_PROMPT = """You are an expert prediction market analyst. Estimate the TRUE probability of the event.

RULES:
- Never give 0% or 100% unless physically impossible or already happened
- Be calibrated: 70% events should happen ~70% of the time
- Account for unknown unknowns by hedging toward 50%
- Consider market manipulation risk
- Lower confidence → less extreme probabilities
- Weight recent news more heavily

Respond ONLY in JSON:
{
  "probability": <1-99>,
  "confidence": <0-100>,
  "reasoning": "<2-3 bullet points>",
  "risk_level": "<low|medium|high|very_high>",
  "factors": {"news_impact": "<positive|negative|neutral>", "momentum": "<bullish|bearish|neutral>", "key_risk": "<string>"}
}"""


@dataclass
class AIModelResult:
    provider: str
    probability: float
    confidence: int
    reasoning: str
    risk_level: str
    factors: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str = ""


@dataclass
class ConsensusResult:
    probability: float
    confidence: int
    reasoning: str
    risk_level: str
    factors: dict[str, Any]
    model_results: list[AIModelResult]
    consensus_spread: float
    models_agree: bool
    num_models_used: int


class MultiAIEngine:
    """Query multiple AI providers and ensemble their predictions."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._providers: list[str] = []
        if self._settings.openai_api_key:
            self._providers.append("openai")
        if self._settings.groq_api_key:
            self._providers.append("groq")
        if self._settings.gemini_api_key:
            self._providers.append("gemini")
        if self._settings.bluesminds_api_key:
            self._providers.append("bluesminds")
        logger.info("multi_ai_init", providers=self._providers)

    async def consensus_estimate(
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
        momentum_data: Optional[dict[str, Any]] = None,
    ) -> ConsensusResult:
        """Get probability estimates from all available AI providers and ensemble."""
        prompt = _build_analysis_prompt(
            market_question, current_yes_price, current_no_price,
            volume, liquidity, news_context, sentiment_data,
            whale_data, category, momentum_data,
        )

        tasks = []
        for provider in self._providers:
            tasks.append(self._query_provider(provider, prompt))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        model_results: list[AIModelResult] = []
        for r in results:
            if isinstance(r, AIModelResult):
                model_results.append(r)
            elif isinstance(r, Exception):
                logger.warning("ai_provider_exception", error=str(r))

        successful = [r for r in model_results if r.success]

        if not successful:
            return ConsensusResult(
                probability=current_yes_price,
                confidence=15,
                reasoning="All AI providers failed. Using market price as fallback.",
                risk_level="very_high",
                factors={},
                model_results=model_results,
                consensus_spread=0.0,
                models_agree=False,
                num_models_used=0,
            )

        return self._ensemble(successful, current_yes_price)

    async def _query_provider(self, provider: str, prompt: str) -> AIModelResult:
        """Query a single AI provider."""
        try:
            if provider == "openai":
                return await self._query_openai(prompt)
            elif provider == "groq":
                return await self._query_groq(prompt)
            elif provider == "gemini":
                return await self._query_gemini(prompt)
            elif provider == "bluesminds":
                return await self._query_bluesminds(prompt)
            else:
                return AIModelResult(
                    provider=provider, probability=0.5, confidence=0,
                    reasoning="Unknown provider", risk_level="high",
                    success=False, error="Unknown provider",
                )
        except Exception as exc:
            logger.warning("ai_query_failed", provider=provider, error=str(exc))
            return AIModelResult(
                provider=provider, probability=0.5, confidence=0,
                reasoning="", risk_level="high",
                success=False, error=str(exc)[:200],
            )

    async def _query_openai(self, prompt: str) -> AIModelResult:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        response = await client.chat.completions.create(
            model=self._settings.openai_model,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
        return _parse_ai_response(response.choices[0].message.content or "{}", "openai")

    async def _query_groq(self, prompt: str) -> AIModelResult:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.groq_model,
                    "messages": [
                        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return _parse_ai_response(content, "groq")

    async def _query_gemini(self, prompt: str) -> AIModelResult:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self._settings.gemini_model}:generateContent",
                params={"key": self._settings.gemini_api_key},
                json={
                    "contents": [{"parts": [{"text": ANALYSIS_SYSTEM_PROMPT + "\n\n" + prompt}]}],
                    "generationConfig": {
                        "temperature": 0.3,
                        "maxOutputTokens": 1500,
                        "responseMimeType": "application/json",
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return _parse_ai_response(content, "gemini")

    async def _query_bluesminds(self, prompt: str) -> AIModelResult:
        """Query Blue Minds API (OpenAI-compatible multi-model proxy)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._settings.bluesminds_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._settings.bluesminds_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.bluesminds_model,
                    "messages": [
                        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return _parse_ai_response(content, "bluesminds")

    def _ensemble(self, results: list[AIModelResult], market_price: float) -> ConsensusResult:
        """Ensemble multiple AI results using confidence-weighted averaging."""
        probabilities = [r.probability for r in results]
        confidences = [r.confidence for r in results]

        total_weight = sum(c for c in confidences) or 1
        weighted_prob = sum(r.probability * r.confidence for r in results) / total_weight
        weighted_prob = max(0.01, min(0.99, weighted_prob))

        spread = max(probabilities) - min(probabilities) if len(probabilities) > 1 else 0.0
        models_agree = spread < 0.15

        if models_agree:
            bonus = min(10, int(len(results) * 5))
        else:
            bonus = -10

        avg_confidence = int(statistics.mean(confidences)) + bonus
        avg_confidence = max(10, min(99, avg_confidence))

        risk_levels = [r.risk_level for r in results]
        risk_order = {"low": 0, "medium": 1, "high": 2, "very_high": 3}
        avg_risk = statistics.mean(risk_order.get(r, 1) for r in risk_levels)
        if avg_risk < 0.5:
            risk = "low"
        elif avg_risk < 1.5:
            risk = "medium"
        elif avg_risk < 2.5:
            risk = "high"
        else:
            risk = "very_high"

        reasoning_parts = []
        for r in results:
            reasoning_parts.append(f"[{r.provider.upper()}] {r.reasoning}")
        consensus_note = "✅ Models AGREE" if models_agree else "⚠️ Models DISAGREE"
        reasoning = f"{consensus_note} (spread: {spread:.1%})\n" + "\n".join(reasoning_parts)

        merged_factors: dict[str, Any] = {}
        for r in results:
            for k, v in r.factors.items():
                if k not in merged_factors:
                    merged_factors[k] = v

        return ConsensusResult(
            probability=round(weighted_prob, 4),
            confidence=avg_confidence,
            reasoning=reasoning,
            risk_level=risk,
            factors=merged_factors,
            model_results=results,
            consensus_spread=round(spread, 4),
            models_agree=models_agree,
            num_models_used=len(results),
        )


def _parse_ai_response(content: str, provider: str) -> AIModelResult:
    """Parse JSON response from any AI provider."""
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            return AIModelResult(
                provider=provider, probability=0.5, confidence=20,
                reasoning="Failed to parse response", risk_level="high",
                success=False, error="JSON parse error",
            )

    prob = float(result.get("probability", 50)) / 100.0
    prob = max(0.01, min(0.99, prob))
    conf = int(result.get("confidence", 50))
    conf = max(0, min(100, conf))

    return AIModelResult(
        provider=provider,
        probability=round(prob, 4),
        confidence=conf,
        reasoning=result.get("reasoning", ""),
        risk_level=result.get("risk_level", "medium"),
        factors=result.get("factors", {}),
        success=True,
    )


def _build_analysis_prompt(
    market_question: str,
    current_yes_price: float,
    current_no_price: float,
    volume: float,
    liquidity: float,
    news_context: Optional[str],
    sentiment_data: Optional[dict[str, Any]],
    whale_data: Optional[dict[str, Any]],
    category: str,
    momentum_data: Optional[dict[str, Any]],
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

    if momentum_data:
        parts.append(
            f"\n## Market Momentum\n"
            f"- 1h change: {momentum_data.get('change_1h', 0):+.2%}\n"
            f"- 6h change: {momentum_data.get('change_6h', 0):+.2%}\n"
            f"- 24h change: {momentum_data.get('change_24h', 0):+.2%}\n"
            f"- Trend: {momentum_data.get('trend', 'neutral')}\n"
            f"- Volatility: {momentum_data.get('volatility', 'unknown')}"
        )

    if news_context:
        parts.append(f"\n## Recent News\n{news_context}")

    if sentiment_data:
        parts.append(
            f"\n## Sentiment Analysis\n"
            f"- Score: {sentiment_data.get('score', 0):.2f} (-1 bearish to +1 bullish)\n"
            f"- Direction: {sentiment_data.get('direction', 'neutral')}\n"
            f"- Momentum: {sentiment_data.get('momentum', 0):.2f}\n"
            f"- Sources: {sentiment_data.get('num_sources', 'unknown')}"
        )

    if whale_data:
        parts.append(
            f"\n## Whale Activity\n"
            f"- Total whale volume: ${whale_data.get('total_whale_volume', 0):,.0f}\n"
            f"- Whale bias: {whale_data.get('whale_bias', 'neutral')}\n"
            f"- Recent whale trades: {whale_data.get('whale_trade_count', 0)}\n"
            f"- Smart money direction: {whale_data.get('smart_money_direction', 'neutral')}"
        )

    parts.append(
        "\nEstimate the TRUE probability of YES. Consider ALL factors above."
    )
    return "\n".join(parts)
