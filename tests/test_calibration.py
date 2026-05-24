"""Tests for calibration engine."""

from src.ai.calibration import CalibrationEngine


def test_bayesian_adjust_basic():
    engine = CalibrationEngine()
    result = engine.bayesian_adjust(
        ai_probability=0.7,
        market_probability=0.5,
        confidence=80,
    )
    assert 0.5 < result.adjusted_probability < 0.8
    assert result.prior_weight >= 0


def test_bayesian_adjust_low_confidence():
    engine = CalibrationEngine()
    result = engine.bayesian_adjust(
        ai_probability=0.9,
        market_probability=0.5,
        confidence=10,
    )
    assert result.adjusted_probability < 0.7


def test_expected_value():
    ev = CalibrationEngine.calculate_expected_value(
        ai_probability=0.7,
        market_price=0.5,
        confidence=80,
    )
    assert ev > 0


def test_kelly_criterion():
    kelly = CalibrationEngine.kelly_criterion(
        ai_probability=0.7,
        market_price=0.5,
    )
    assert kelly > 0
    assert kelly < 1


def test_information_ratio():
    ir = CalibrationEngine.information_ratio(0.7, 0.5)
    assert ir > 0
