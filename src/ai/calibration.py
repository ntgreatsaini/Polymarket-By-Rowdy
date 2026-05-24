"""Confidence calibration and Bayesian adjustment for AI predictions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CalibrationResult:
    adjusted_probability: float
    calibration_factor: float
    prior_weight: float
    posterior_probability: float


class CalibrationEngine:
    """Bayesian calibration engine for adjusting AI probability estimates."""

    def __init__(
        self,
        prior_accuracy: float = 0.65,
        min_confidence_weight: float = 0.3,
        max_confidence_weight: float = 0.9,
    ) -> None:
        self.prior_accuracy = prior_accuracy
        self.min_confidence_weight = min_confidence_weight
        self.max_confidence_weight = max_confidence_weight
        self._historical_accuracy: dict[str, list[float]] = {}

    def bayesian_adjust(
        self,
        ai_probability: float,
        market_probability: float,
        confidence: int,
        category: Optional[str] = None,
    ) -> CalibrationResult:
        """Apply Bayesian adjustment to AI probability estimate."""
        confidence_weight = self._confidence_to_weight(confidence)

        prior = market_probability
        if category and category in self._historical_accuracy:
            hist = self._historical_accuracy[category]
            if hist:
                accuracy = sum(hist) / len(hist)
                confidence_weight *= accuracy

        posterior = (
            confidence_weight * ai_probability
            + (1 - confidence_weight) * prior
        )

        posterior = max(0.01, min(0.99, posterior))

        calibration_factor = posterior / ai_probability if ai_probability > 0 else 1.0

        return CalibrationResult(
            adjusted_probability=round(posterior, 4),
            calibration_factor=round(calibration_factor, 4),
            prior_weight=round(1 - confidence_weight, 4),
            posterior_probability=round(posterior, 4),
        )

    def _confidence_to_weight(self, confidence: int) -> float:
        """Map confidence score (0-100) to a weight between min and max."""
        normalized = confidence / 100.0
        weight_range = self.max_confidence_weight - self.min_confidence_weight
        return self.min_confidence_weight + (normalized * weight_range)

    def update_accuracy(self, category: str, was_correct: bool) -> None:
        """Update historical accuracy for a category."""
        if category not in self._historical_accuracy:
            self._historical_accuracy[category] = []
        self._historical_accuracy[category].append(1.0 if was_correct else 0.0)
        if len(self._historical_accuracy[category]) > 500:
            self._historical_accuracy[category] = self._historical_accuracy[category][-500:]

    @staticmethod
    def calculate_expected_value(
        ai_probability: float,
        market_price: float,
        confidence: int,
    ) -> float:
        """Calculate expected value of a trade."""
        if market_price <= 0 or market_price >= 1:
            return 0.0
        ev_yes = ai_probability * (1.0 / market_price - 1.0) - (1 - ai_probability)
        return round(ev_yes * 100, 2)

    @staticmethod
    def kelly_criterion(
        ai_probability: float,
        market_price: float,
        fraction: float = 0.25,
    ) -> float:
        """Calculate Kelly criterion bet sizing (fractional)."""
        if market_price <= 0 or market_price >= 1:
            return 0.0
        b = (1.0 / market_price) - 1.0
        if b <= 0:
            return 0.0
        kelly = (ai_probability * b - (1 - ai_probability)) / b
        return round(max(0, kelly * fraction), 4)

    @staticmethod
    def information_ratio(
        ai_probability: float,
        market_probability: float,
    ) -> float:
        """Calculate KL divergence between AI and market probability distributions."""
        if ai_probability <= 0 or ai_probability >= 1:
            return 0.0
        if market_probability <= 0 or market_probability >= 1:
            return 0.0
        kl = ai_probability * math.log(ai_probability / market_probability) + (
            1 - ai_probability
        ) * math.log((1 - ai_probability) / (1 - market_probability))
        return round(kl, 6)
