"""Tests for Polymarket client parsing."""

from src.polymarket.client import PolymarketClient


def test_parse_market_basic():
    raw = {
        "conditionId": "0xabc123",
        "question": "Will BTC hit $100k?",
        "slug": "btc-100k",
        "tokens": [
            {"outcome": "Yes", "price": 0.45},
            {"outcome": "No", "price": 0.55},
        ],
        "volume": 150000,
        "liquidity": 75000,
        "active": True,
        "tags": ["crypto"],
    }
    parsed = PolymarketClient.parse_market(raw)
    assert parsed["condition_id"] == "0xabc123"
    assert parsed["yes_price"] == 0.45
    assert parsed["no_price"] == 0.55
    assert parsed["category"] == "crypto"
    assert parsed["is_active"] is True


def test_parse_market_with_outcome_prices():
    raw = {
        "conditionId": "0xdef456",
        "question": "Will the election be contested?",
        "outcomePrices": "[0.35, 0.65]",
        "volume": 50000,
        "liquidity": 20000,
        "active": True,
        "tags": ["politics"],
    }
    parsed = PolymarketClient.parse_market(raw)
    assert parsed["yes_price"] == 0.35
    assert parsed["no_price"] == 0.65
    assert parsed["category"] == "politics"


def test_parse_market_empty_tokens():
    raw = {
        "conditionId": "0xempty",
        "question": "Unknown market",
        "tokens": [],
        "volume": 0,
        "liquidity": 0,
    }
    parsed = PolymarketClient.parse_market(raw)
    assert parsed["yes_price"] == 0.0
    assert parsed["no_price"] == 0.0


def test_classify_sports():
    raw = {
        "conditionId": "0xsport",
        "question": "Will the Lakers win the NBA Championship?",
        "tokens": [],
        "volume": 10000,
        "liquidity": 5000,
        "tags": ["sports"],
    }
    parsed = PolymarketClient.parse_market(raw)
    assert parsed["category"] == "sports"
