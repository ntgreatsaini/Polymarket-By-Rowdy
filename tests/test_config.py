"""Tests for configuration module."""

import os

import pytest


def test_env_example_exists():
    """Verify .env.example is present in the repo."""
    assert os.path.isfile(
        os.path.join(os.path.dirname(__file__), "..", ".env.example")
    )


def test_settings_defaults():
    """Verify Settings can be instantiated with required env vars."""
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
    os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
    os.environ.setdefault("OPENAI_API_KEY", "test-key")

    from src.config.settings import Settings

    s = Settings(
        telegram_bot_token="test",
        telegram_chat_id="123",
        openai_api_key="sk-test",
    )
    assert s.openai_model == "gpt-4o-mini"
    assert s.signal_min_confidence == 65
    assert not s.is_production


def test_log_level_validation():
    """Verify log level validation."""
    from src.config.settings import Settings

    s = Settings(
        telegram_bot_token="t",
        telegram_chat_id="1",
        openai_api_key="k",
        log_level="debug",
    )
    assert s.log_level == "DEBUG"

    with pytest.raises(Exception):
        Settings(
            telegram_bot_token="t",
            telegram_chat_id="1",
            openai_api_key="k",
            log_level="invalid",
        )
