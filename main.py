"""Main entry point for the Polymarket Telegram Bot."""

from __future__ import annotations

import asyncio
import sys

import structlog
import uvicorn

from src.ai.calibration import CalibrationEngine
from src.ai.multi_ai_engine import MultiAIEngine
from src.ai.probability_engine import AIProbabilityEngine
from src.api.app import create_api_app
from src.config.logging_config import setup_logging
from src.config.settings import get_settings, validate_settings
from src.database.session import init_db
from src.polymarket.client import PolymarketClient
from src.polymarket.momentum import MomentumTracker
from src.scheduler.jobs import JobManager
from src.sentiment.analyzer import SentimentAnalyzer
from src.sentiment.enhanced_sources import EnhancedDataSources
from src.sentiment.news_fetcher import NewsFetcher
from src.signals.generator import SignalGenerator
from src.telegram.bot import PolymarketBot
from src.whales.tracker import WhaleTracker

logger = structlog.get_logger(__name__)


async def run_bot() -> None:
    """Initialize and run the Telegram bot with all components."""
    validate_settings()
    settings = get_settings()
    setup_logging(settings.log_level)

    logger.info("initializing_bot", env=settings.app_env)

    await init_db()

    poly_client = PolymarketClient()
    ai_engine = AIProbabilityEngine()
    news_fetcher = NewsFetcher()
    sentiment_analyzer = SentimentAnalyzer()
    whale_tracker = WhaleTracker(poly_client)
    calibration = CalibrationEngine()
    momentum_tracker = MomentumTracker(poly_client)
    enhanced_sources = EnhancedDataSources()

    # Multi-AI Consensus Engine (uses all available providers)
    multi_ai = MultiAIEngine()
    ai_providers = []
    if settings.openai_api_key:
        ai_providers.append("OpenAI")
    if settings.groq_api_key:
        ai_providers.append("Groq")
    if settings.gemini_api_key:
        ai_providers.append("Gemini")

    signal_generator = SignalGenerator(
        polymarket_client=poly_client,
        ai_engine=ai_engine,
        news_fetcher=news_fetcher,
        sentiment_analyzer=sentiment_analyzer,
        whale_tracker=whale_tracker,
        calibration_engine=calibration,
        multi_ai_engine=multi_ai if len(ai_providers) > 0 else None,
        momentum_tracker=momentum_tracker,
        enhanced_sources=enhanced_sources,
    )

    bot = PolymarketBot(signal_generator)
    app = bot.build_app()

    job_manager = JobManager(
        signal_generator=signal_generator,
        telegram_bot=bot,
        whale_tracker=whale_tracker,
    )
    job_manager.setup_jobs()
    job_manager.start()

    logger.info(
        "bot_started",
        chat_id=settings.telegram_chat_id,
        scan_interval=settings.scan_interval_seconds,
        ai_providers=ai_providers,
    )

    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)  # type: ignore[union-attr]

        # Keep running
        stop_event = asyncio.Event()
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("bot_shutting_down")
    finally:
        job_manager.stop()
        await app.updater.stop()  # type: ignore[union-attr]
        await app.stop()
        await app.shutdown()
        await poly_client.close()
        await news_fetcher.close()
        logger.info("bot_stopped")


def run_api() -> None:
    """Run the FastAPI admin API."""
    validate_settings()
    settings = get_settings()
    setup_logging(settings.log_level)
    api_app = create_api_app()
    uvicorn.run(api_app, host="0.0.0.0", port=8000)


def main() -> None:
    """Main entry point — runs bot by default, or API with --api flag."""
    if "--api" in sys.argv:
        run_api()
    else:
        asyncio.run(run_bot())


if __name__ == "__main__":
    main()
