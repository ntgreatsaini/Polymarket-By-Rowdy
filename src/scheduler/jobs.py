"""Scheduled jobs for market scanning, alerts, and performance tracking."""

from __future__ import annotations

from typing import Any, Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


class JobManager:
    """Manages all scheduled jobs for the bot."""

    def __init__(
        self,
        signal_generator: Any,
        telegram_bot: Any,
        whale_tracker: Any,
    ) -> None:
        self._signal_gen = signal_generator
        self._bot = telegram_bot
        self._whales = whale_tracker
        self._settings = get_settings()
        self._scheduler = get_scheduler()
        self._is_running = False

    def setup_jobs(self) -> None:
        """Register all scheduled jobs."""
        scan_interval = self._settings.scan_interval_seconds

        self._scheduler.add_job(
            self._scan_and_alert,
            "interval",
            seconds=scan_interval,
            id="signal_scan",
            replace_existing=True,
            max_instances=1,
        )

        self._scheduler.add_job(
            self._whale_scan,
            "interval",
            seconds=max(120, scan_interval // 2),
            id="whale_scan",
            replace_existing=True,
            max_instances=1,
        )

        self._scheduler.add_job(
            self._market_snapshot,
            "interval",
            minutes=30,
            id="market_snapshot",
            replace_existing=True,
            max_instances=1,
        )

        self._scheduler.add_job(
            self._performance_update,
            "cron",
            hour=0,
            minute=0,
            id="daily_performance",
            replace_existing=True,
        )

        self._scheduler.add_job(
            self._clear_signal_cache,
            "interval",
            hours=6,
            id="clear_cache",
            replace_existing=True,
        )

        logger.info("jobs_registered", scan_interval=scan_interval)

    def start(self) -> None:
        if not self._is_running:
            self._scheduler.start()
            self._is_running = True
            logger.info("scheduler_started")

    def stop(self) -> None:
        if self._is_running:
            self._scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("scheduler_stopped")

    async def _scan_and_alert(self) -> None:
        """Scan markets and send alerts for new signals."""
        try:
            logger.info("signal_scan_job_start")
            signals = await self._signal_gen.scan_and_generate(max_markets=50)

            if not signals:
                logger.info("signal_scan_no_signals")
                return

            chat_id = self._settings.telegram_chat_id
            for signal in signals[:5]:
                await self._bot.send_signal_to_chat(chat_id, signal)

            logger.info("signal_scan_job_complete", signals_sent=min(len(signals), 5))

        except Exception as exc:
            logger.error("signal_scan_job_error", error=str(exc))

    async def _whale_scan(self) -> None:
        """Scan for whale trades and send alerts."""
        try:
            alerts = await self._whales.scan_for_whale_trades()
            significant = [a for a in alerts if a.amount >= self._settings.whale_min_trade_size * 3]

            if not significant:
                return

            chat_id = self._settings.telegram_chat_id
            for alert in significant[:3]:
                await self._bot.send_whale_alert_to_chat(chat_id, alert)

            logger.info("whale_scan_complete", alerts_sent=min(len(significant), 3))

        except Exception as exc:
            logger.error("whale_scan_error", error=str(exc))

    async def _market_snapshot(self) -> None:
        """Take periodic market snapshots for historical tracking."""
        try:
            logger.debug("market_snapshot_job")
        except Exception as exc:
            logger.error("snapshot_error", error=str(exc))

    async def _performance_update(self) -> None:
        """Daily performance metrics update."""
        try:
            logger.info("daily_performance_update")
        except Exception as exc:
            logger.error("performance_update_error", error=str(exc))

    async def _clear_signal_cache(self) -> None:
        """Periodically clear the signal deduplication cache."""
        self._signal_gen.clear_recent_signals()
        logger.info("signal_cache_cleared")
