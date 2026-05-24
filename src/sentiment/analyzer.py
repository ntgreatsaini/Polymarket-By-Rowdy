"""Multi-source sentiment analysis engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = structlog.get_logger(__name__)


@dataclass
class SentimentResult:
    score: float  # -1 (bearish) to +1 (bullish)
    direction: str  # bullish, bearish, neutral
    momentum: float  # rate of change
    confidence: float  # 0 to 1
    sample_size: int
    sources: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class SentimentAnalyzer:
    """Aggregated sentiment analysis using VADER and text classification."""

    def __init__(self) -> None:
        self._vader = SentimentIntensityAnalyzer()

    def analyze_texts(
        self,
        texts: list[str],
        source: str = "unknown",
    ) -> SentimentResult:
        """Analyze sentiment from a list of text samples."""
        if not texts:
            return SentimentResult(
                score=0.0,
                direction="neutral",
                momentum=0.0,
                confidence=0.0,
                sample_size=0,
            )

        scores: list[float] = []
        for text in texts:
            vs = self._vader.polarity_scores(text)
            scores.append(vs["compound"])

        avg_score = sum(scores) / len(scores)

        if len(scores) > 5:
            recent = scores[-len(scores) // 3 :]
            older = scores[: len(scores) // 3]
            momentum = (sum(recent) / len(recent)) - (sum(older) / len(older))
        else:
            momentum = 0.0

        confidence = min(1.0, len(scores) / 20.0)

        if avg_score > 0.15:
            direction = "bullish"
        elif avg_score < -0.15:
            direction = "bearish"
        else:
            direction = "neutral"

        return SentimentResult(
            score=round(avg_score, 4),
            direction=direction,
            momentum=round(momentum, 4),
            confidence=round(confidence, 4),
            sample_size=len(texts),
            sources=[source],
            details={
                "min_score": round(min(scores), 4),
                "max_score": round(max(scores), 4),
                "positive_ratio": round(sum(1 for s in scores if s > 0.05) / len(scores), 4),
                "negative_ratio": round(sum(1 for s in scores if s < -0.05) / len(scores), 4),
            },
        )

    def aggregate_sentiments(
        self,
        results: list[SentimentResult],
    ) -> SentimentResult:
        """Combine sentiment results from multiple sources with weighting."""
        if not results:
            return SentimentResult(
                score=0.0, direction="neutral", momentum=0.0,
                confidence=0.0, sample_size=0,
            )

        total_weight = 0.0
        weighted_score = 0.0
        weighted_momentum = 0.0
        total_samples = 0
        all_sources: list[str] = []

        for r in results:
            weight = r.confidence * r.sample_size
            if weight == 0:
                weight = 0.1
            weighted_score += r.score * weight
            weighted_momentum += r.momentum * weight
            total_weight += weight
            total_samples += r.sample_size
            all_sources.extend(r.sources)

        if total_weight > 0:
            final_score = weighted_score / total_weight
            final_momentum = weighted_momentum / total_weight
        else:
            final_score = 0.0
            final_momentum = 0.0

        confidence = min(1.0, total_samples / 50.0)

        if final_score > 0.15:
            direction = "bullish"
        elif final_score < -0.15:
            direction = "bearish"
        else:
            direction = "neutral"

        return SentimentResult(
            score=round(final_score, 4),
            direction=direction,
            momentum=round(final_momentum, 4),
            confidence=round(confidence, 4),
            sample_size=total_samples,
            sources=list(set(all_sources)),
        )

    def detect_hype(self, texts: list[str], threshold: float = 0.7) -> bool:
        """Detect if texts show signs of hype/manipulation."""
        if not texts:
            return False
        scores = [self._vader.polarity_scores(t)["compound"] for t in texts]
        extreme_count = sum(1 for s in scores if abs(s) > threshold)
        ratio = extreme_count / len(scores) if scores else 0
        return ratio > 0.6

    def detect_bot_activity(self, texts: list[str]) -> float:
        """Estimate proportion of bot-like activity (0 to 1)."""
        if not texts:
            return 0.0
        unique_texts = set(t.strip().lower() for t in texts)
        uniqueness_ratio = len(unique_texts) / len(texts)
        bot_score = 1.0 - uniqueness_ratio
        return round(max(0.0, bot_score), 4)
