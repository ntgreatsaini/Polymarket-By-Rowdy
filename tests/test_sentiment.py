"""Tests for sentiment analyzer."""

from src.sentiment.analyzer import SentimentAnalyzer


def test_analyze_bullish_texts():
    analyzer = SentimentAnalyzer()
    texts = [
        "Bitcoin is soaring to new all-time highs!",
        "Amazing rally in crypto markets today!",
        "Institutional investors are flooding in!",
    ]
    result = analyzer.analyze_texts(texts, source="test")
    assert result.score > 0
    assert result.direction == "bullish"
    assert result.sample_size == 3


def test_analyze_bearish_texts():
    analyzer = SentimentAnalyzer()
    texts = [
        "Market crash incoming, sell everything!",
        "Terrible losses across all sectors.",
        "Economy in deep recession, no recovery in sight.",
    ]
    result = analyzer.analyze_texts(texts, source="test")
    assert result.score < 0
    assert result.direction == "bearish"


def test_analyze_empty():
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze_texts([], source="test")
    assert result.score == 0
    assert result.direction == "neutral"
    assert result.sample_size == 0


def test_detect_hype():
    analyzer = SentimentAnalyzer()
    hype_texts = [
        "INCREDIBLE! BEST THING EVER!!! AMAZING!!!",
        "ABSOLUTELY STUNNING FANTASTIC!!!",
        "THIS IS THE GREATEST! WOW! INCREDIBLE!",
    ]
    assert analyzer.detect_hype(hype_texts, threshold=0.5)


def test_aggregate_sentiments():
    analyzer = SentimentAnalyzer()
    r1 = analyzer.analyze_texts(["Great news!"], source="a")
    r2 = analyzer.analyze_texts(["Bad news..."], source="b")
    agg = analyzer.aggregate_sentiments([r1, r2])
    assert agg.sample_size == 2
    assert len(agg.sources) == 2
