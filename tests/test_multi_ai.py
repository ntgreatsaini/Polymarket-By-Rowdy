"""Tests for Multi-AI Consensus Engine."""

from src.ai.multi_ai_engine import _parse_ai_response, _build_analysis_prompt


def test_parse_ai_response_valid():
    content = '{"probability": 65, "confidence": 80, "reasoning": "Test", "risk_level": "medium", "factors": {"news_impact": "positive"}}'
    result = _parse_ai_response(content, "test")
    assert result.success
    assert result.provider == "test"
    assert 0.6 <= result.probability <= 0.7
    assert result.confidence == 80
    assert result.risk_level == "medium"


def test_parse_ai_response_clamp():
    content = '{"probability": 150, "confidence": 200}'
    result = _parse_ai_response(content, "test")
    assert result.probability == 0.99
    assert result.confidence == 100


def test_parse_ai_response_invalid_json():
    content = "not json at all"
    result = _parse_ai_response(content, "test")
    assert not result.success


def test_parse_ai_response_embedded_json():
    content = 'Here is my analysis: {"probability": 45, "confidence": 70, "reasoning": "test"} end'
    result = _parse_ai_response(content, "test")
    assert result.success
    assert 0.44 <= result.probability <= 0.46


def test_build_prompt_basic():
    prompt = _build_analysis_prompt(
        "Will BTC hit 100k?", 0.5, 0.5, 100000, 50000,
        None, None, None, "crypto", None,
    )
    assert "BTC" in prompt
    assert "crypto" in prompt
    assert "100,000" in prompt or "$100,000" in prompt


def test_build_prompt_with_momentum():
    prompt = _build_analysis_prompt(
        "Test?", 0.5, 0.5, 1000, 1000, None, None, None, "other",
        {"change_1h": 0.05, "change_6h": 0.1, "change_24h": 0.2, "trend": "bullish", "volatility": "high"},
    )
    assert "Momentum" in prompt
    assert "bullish" in prompt
