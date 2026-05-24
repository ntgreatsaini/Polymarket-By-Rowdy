"""Multi-source sentiment analysis engine — VADER + TextBlob ensemble."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from textblob import TextBlob
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


# Source reliability weights — higher = more trusted
SOURCE_WEIGHTS: dict[str, float] = {
    "google_news": 1.0,
    "newsapi": 0.9,
    "gdelt": 0.8,
    "reuters": 1.0,
    "bbc": 0.95,
    "reddit": 0.5,
    "hackernews": 0.7,
    "twitter": 0.4,
    "unknown": 0.6,
    "news": 0.8,
}


class SentimentAnalyzer:
    """Aggregated sentiment analysis using VADER + TextBlob ensemble."""

    def __init__(self) -> None:
        self._vader = SentimentIntensityAnalyzer()

    def analyze_texts(
        self,
        texts: list[str],
        source: str = "unknown",
    ) -> SentimentResult:
        """Analyze sentiment using VADER + TextBlob ensemble."""
        if not texts:
            return SentimentResult(
                score=0.0, direction="neutral", momentum=0.0,
                confidence=0.0, sample_size=0,
            )

        vader_scores: list[float] = []
        textblob_scores: list[float] = []
        ensemble_scores: list[float] = []

        for text in texts:
            vs = self._vader.polarity_scores(text)
            vader_score = vs["compound"]
            vader_scores.append(vader_score)

            try:
                blob = TextBlob(text)
                tb_score = blob.sentiment.polarity  # -1 to +1
                textblob_scores.append(tb_score)
            except Exception:
                tb_score = vader_score
                textblob_scores.append(tb_score)

            # Ensemble: 60% VADER (better for social/news), 40% TextBlob (better for subjectivity)
            combined = 0.6 * vader_score + 0.4 * tb_score
            ensemble_scores.append(combined)

        avg_score = sum(ensemble_scores) / len(ensemble_scores)
        source_weight = SOURCE_WEIGHTS.get(source, 0.6)
        avg_score *= source_weight

        if len(ensemble_scores) > 5:
            recent = ensemble_scores[-len(ensemble_scores) // 3:]
            older = ensemble_scores[:len(ensemble_scores) // 3]
            momentum = (sum(recent) / len(recent)) - (sum(older) / len(older))
        else:
            momentum = 0.0

        confidence = min(1.0, len(ensemble_scores) / 20.0) * source_weight

        # Agreement bonus: if VADER and TextBlob agree, boost confidence
        vader_avg = sum(vader_scores) / len(vader_scores)
        tb_avg = sum(textblob_scores) / len(textblob_scores)
        if (vader_avg > 0 and tb_avg > 0) or (vader_avg < 0 and tb_avg < 0):
            confidence = min(1.0, confidence * 1.15)

        if avg_score > 0.12:
            direction = "bullish"
        elif avg_score < -0.12:
            direction = "bearish"
        else:
            direction = "neutral"

        # Subjectivity analysis via TextBlob
        subjectivities = []
        for text in texts[:20]:
            try:
                subjectivities.append(TextBlob(text).sentiment.subjectivity)
            except Exception:
                pass
        avg_subjectivity = sum(subjectivities) / len(subjectivities) if subjectivities else 0.5

        return SentimentResult(
            score=round(avg_score, 4),
            direction=direction,
            momentum=round(momentum, 4),
            confidence=round(confidence, 4),
            sample_size=len(texts),
            sources=[source],
            details={
                "vader_avg": round(vader_avg, 4),
                "textblob_avg": round(tb_avg, 4),
                "min_score": round(min(ensemble_scores), 4),
                "max_score": round(max(ensemble_scores), 4),
                "positive_ratio": round(sum(1 for s in ensemble_scores if s > 0.05) / len(ensemble_scores), 4),
                "negative_ratio": round(sum(1 for s in ensemble_scores if s < -0.05) / len(ensemble_scores), 4),
                "avg_subjectivity": round(avg_subjectivity, 4),
                "vader_textblob_agree": (vader_avg > 0 and tb_avg > 0) or (vader_avg < 0 and tb_avg < 0),
                "source_weight": source_weight,
            },
        )

    def aggregate_sentiments(
        self,
        results: list[SentimentResult],
    ) -> SentimentResult:
        """Combine sentiment results from multiple sources with reliability weighting."""
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
            source_w = max(SOURCE_WEIGHTS.get(s, 0.6) for s in r.sources) if r.sources else 0.6
            weight = r.confidence * r.sample_size * source_w
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
        num_sources = len(set(all_sources))
        if num_sources >= 3:
            confidence = min(1.0, confidence * 1.1)

        if final_score > 0.12:
            direction = "bullish"
        elif final_score < -0.12:
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
