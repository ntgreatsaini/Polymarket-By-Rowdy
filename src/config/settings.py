"""Application settings loaded from environment variables."""

from __future__ import annotations

import sys
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: str = Field(..., description="Telegram bot API token")
    telegram_chat_id: str = Field(..., description="Default Telegram chat ID for alerts")

    # --- OpenAI ---
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field("gpt-4o-mini", description="OpenAI model to use")

    # --- News ---
    news_api_key: str = Field("", description="NewsAPI.org key")
    gdelt_api_url: str = Field(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        description="GDELT API URL",
    )

    # --- Crypto ---
    coingecko_api_key: str = Field("", description="CoinGecko API key")
    coingecko_base_url: str = Field(
        "https://api.coingecko.com/api/v3",
        description="CoinGecko base URL",
    )

    # --- Financial ---
    fred_api_key: str = Field("", description="FRED API key")

    # --- Sports/Odds ---
    the_odds_api_key: str = Field("", description="The Odds API key")

    # --- Polymarket ---
    polymarket_gamma_api: str = Field(
        "https://gamma-api.polymarket.com",
        description="Polymarket Gamma API base URL",
    )
    polymarket_data_api: str = Field(
        "https://data-api.polymarket.com",
        description="Polymarket Data API base URL",
    )
    polymarket_clob_api: str = Field(
        "https://clob.polymarket.com",
        description="Polymarket CLOB API base URL",
    )

    # --- Database ---
    database_url: str = Field(
        "sqlite+aiosqlite:///./polymarket_bot.db",
        description="Async database URL",
    )
    database_url_sync: str = Field(
        "sqlite:///./polymarket_bot.db",
        description="Sync database URL (for Alembic)",
    )

    # --- Redis ---
    redis_url: str = Field("redis://localhost:6379/0", description="Redis URL")

    # --- App ---
    app_env: str = Field("development", description="Application environment")
    log_level: str = Field("INFO", description="Log level")
    signal_min_confidence: int = Field(65, ge=0, le=100)
    signal_min_liquidity: float = Field(5000.0, ge=0)
    whale_min_trade_size: float = Field(1000.0, ge=0)
    scan_interval_seconds: int = Field(300, ge=30)
    alert_cooldown_seconds: int = Field(1800, ge=60)

    # --- Branding ---
    telegram_channel_link: str = Field("https://t.me/RowdyxCrypto")
    x_profile_link: str = Field("https://x.com/0xRowdyBhai")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return cached settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def validate_settings() -> None:
    """Validate all required settings are present on startup."""
    try:
        s = get_settings()
        missing: list[str] = []
        if not s.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not s.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if missing:
            print(f"[FATAL] Missing required env vars: {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)
    except Exception as exc:
        print(f"[FATAL] Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)
