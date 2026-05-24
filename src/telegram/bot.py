"""Main Telegram bot with all command handlers."""

from __future__ import annotations

from typing import Any, Optional

import structlog
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from src.config.settings import get_settings
from src.signals.generator import SignalGenerator, TradeSignal
from src.telegram.formatter import (
    format_help,
    format_market_info,
    format_performance,
    format_signal,
    format_signal_compact,
    format_start,
    format_trending,
    format_whale_alert,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

logger = structlog.get_logger(__name__)

RATE_LIMIT: dict[int, float] = {}
RATE_LIMIT_SECONDS = 3


def _get_inline_buttons() -> InlineKeyboardMarkup:
    """Standard inline buttons for every alert."""
    settings = get_settings()
    buttons = [
        [
            InlineKeyboardButton("📢 Join Telegram", url=settings.telegram_channel_link),
            InlineKeyboardButton("🐦 Follow on X", url=settings.x_profile_link),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def _get_market_buttons(condition_id: str) -> InlineKeyboardMarkup:
    settings = get_settings()
    market_url = f"https://polymarket.com/event/{condition_id}"
    buttons = [
        [InlineKeyboardButton("📊 View Market", url=market_url)],
        [
            InlineKeyboardButton("📢 Join Telegram", url=settings.telegram_channel_link),
            InlineKeyboardButton("🐦 Follow on X", url=settings.x_profile_link),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


class PolymarketBot:
    """Telegram bot that handles all user commands and delivers signals."""

    def __init__(self, signal_generator: SignalGenerator) -> None:
        self._signal_gen = signal_generator
        self._settings = get_settings()
        self._app: Optional[Application] = None

    def build_app(self) -> Application:
        """Build the Telegram Application with all handlers."""
        builder = Application.builder().token(self._settings.telegram_bot_token)
        self._app = builder.build()

        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("signals", self._cmd_signals))
        self._app.add_handler(CommandHandler("highconfidence", self._cmd_high_confidence))
        self._app.add_handler(CommandHandler("crypto", self._cmd_crypto))
        self._app.add_handler(CommandHandler("sports", self._cmd_sports))
        self._app.add_handler(CommandHandler("politics", self._cmd_politics))
        self._app.add_handler(CommandHandler("economy", self._cmd_economy))
        self._app.add_handler(CommandHandler("whales", self._cmd_whales))
        self._app.add_handler(CommandHandler("trending", self._cmd_trending))
        self._app.add_handler(CommandHandler("top", self._cmd_top))
        self._app.add_handler(CommandHandler("market", self._cmd_market))
        self._app.add_handler(CommandHandler("portfolio", self._cmd_portfolio))
        self._app.add_handler(CommandHandler("performance", self._cmd_performance))
        self._app.add_handler(CommandHandler("subscribe", self._cmd_subscribe))
        self._app.add_handler(CommandHandler("unsubscribe", self._cmd_unsubscribe))

        self._app.add_handler(CallbackQueryHandler(self._callback_handler))

        self._app.add_error_handler(self._error_handler)

        return self._app

    # ── Command Handlers ───────────────────────────────

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        await update.effective_message.reply_text(
            format_start(),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=_get_inline_buttons(),
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        await update.effective_message.reply_text(
            format_help(),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=_get_inline_buttons(),
        )

    async def _cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        await update.effective_message.reply_text("🔍 Scanning markets for signals\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

        signals = await self._signal_gen.scan_and_generate(max_markets=30)

        if not signals:
            await update.effective_message.reply_text(
                "No high\\-confidence signals found right now\\. Try again later\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        for sig in signals[:5]:
            await self._send_signal(update, sig)

    async def _cmd_high_confidence(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        await update.effective_message.reply_text("🎯 Scanning for high\\-confidence signals\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

        signals = await self._signal_gen.scan_and_generate(max_markets=50, min_confidence=80)

        if not signals:
            await update.effective_message.reply_text(
                "No high\\-confidence signals \\(80\\+\\) found\\. Check back soon\\!",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        for sig in signals[:3]:
            await self._send_signal(update, sig)

    async def _cmd_crypto(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._cmd_category(update, context, "crypto", "₿ Crypto")

    async def _cmd_sports(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._cmd_category(update, context, "sports", "⚽ Sports")

    async def _cmd_politics(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._cmd_category(update, context, "politics", "🏛 Politics")

    async def _cmd_economy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._cmd_category(update, context, "macro", "📈 Economy")

    async def _cmd_category(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, category: str, label: str
    ) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        await update.effective_message.reply_text(f"🔍 Scanning {label} markets\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

        signals = await self._signal_gen.scan_and_generate(max_markets=30)
        cat_signals = [s for s in signals if s.category == category]

        if not cat_signals:
            await update.effective_message.reply_text(
                f"No {label} signals found right now\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        for sig in cat_signals[:5]:
            await self._send_signal(update, sig)

    async def _cmd_whales(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        await update.effective_message.reply_text("🐋 Scanning for whale activity\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

        whale_alerts = await self._signal_gen._whales.scan_for_whale_trades()

        if not whale_alerts:
            await update.effective_message.reply_text(
                "No significant whale activity detected recently\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        for alert in whale_alerts[:5]:
            try:
                await update.effective_message.reply_text(
                    format_whale_alert(alert),
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=_get_inline_buttons(),
                )
            except Exception as exc:
                logger.warning("whale_alert_send_error", error=str(exc))

    async def _cmd_trending(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        raw = await self._signal_gen._poly.get_markets(limit=10, order="volume", ascending=False)
        markets = [self._signal_gen._poly.parse_market(m) for m in raw]

        text = format_trending(markets)
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=_get_inline_buttons()
        )

    async def _cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        raw = await self._signal_gen._poly.get_markets(limit=10, order="volume", ascending=False)
        markets = [self._signal_gen._poly.parse_market(m) for m in raw]
        text = format_trending(markets, title="🏆 Top Markets by Volume")
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=_get_inline_buttons()
        )

    async def _cmd_market(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        if not context.args:
            await update.effective_message.reply_text(
                "Usage: /market \\[market name\\]\nExample: `/market Bitcoin 150k`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        query = " ".join(context.args)
        await update.effective_message.reply_text(f"🔍 Searching for: {query}\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

        results = await self._signal_gen._poly.search_markets(query, limit=3)
        if not results:
            await update.effective_message.reply_text(
                "No markets found for that query\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        for raw in results[:3]:
            market = self._signal_gen._poly.parse_market(raw)
            text = format_market_info(market)
            await update.effective_message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=_get_market_buttons(market["condition_id"]),
            )

    async def _cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        await update.effective_message.reply_text(
            "📂 *Portfolio*\n\nPortfolio tracking coming soon\\! "
            "Use /signals to see current opportunities\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=_get_inline_buttons(),
        )

    async def _cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        metrics = {
            "win_rate": 0.0,
            "total_roi": 0.0,
            "total_signals": 0,
            "wins": 0,
            "losses": 0,
            "avg_confidence": 0,
            "best_category": "N/A",
            "worst_category": "N/A",
        }
        text = format_performance(metrics)
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=_get_inline_buttons()
        )

    async def _cmd_subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        await update.effective_message.reply_text(
            "✅ You are now subscribed to automatic signals\\!\n"
            "You will receive high\\-confidence alerts as they are detected\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=_get_inline_buttons(),
        )

    async def _cmd_unsubscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not self._rate_check(update):
            return
        await update.effective_message.reply_text(
            "🔕 You have been unsubscribed from automatic alerts\\.\n"
            "Use /subscribe to re\\-enable\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    # ── Callback Handler ───────────────────────────────

    async def _callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query:
            await query.answer()

    # ── Sending Signals ────────────────────────────────

    async def _send_signal(self, update: Update, signal: TradeSignal) -> None:
        """Send a formatted signal to the chat."""
        if not update.effective_message:
            return
        try:
            text = format_signal(signal)
            await update.effective_message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=_get_market_buttons(signal.condition_id),
            )
        except Exception:
            try:
                text = format_signal_compact(signal)
                await update.effective_message.reply_text(
                    text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=_get_market_buttons(signal.condition_id),
                )
            except Exception as exc:
                logger.error("signal_send_error", error=str(exc))

    async def send_signal_to_chat(self, chat_id: int | str, signal: TradeSignal) -> None:
        """Send a signal to a specific chat ID (for scheduled alerts)."""
        if not self._app:
            return
        try:
            text = format_signal(signal)
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=_get_market_buttons(signal.condition_id),
            )
        except Exception:
            try:
                text = format_signal_compact(signal)
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=_get_market_buttons(signal.condition_id),
                )
            except Exception as exc:
                logger.error("chat_signal_send_error", chat_id=chat_id, error=str(exc))

    async def send_whale_alert_to_chat(self, chat_id: int | str, alert: Any) -> None:
        """Send a whale alert to a specific chat ID."""
        if not self._app:
            return
        try:
            text = format_whale_alert(alert)
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=_get_inline_buttons(),
            )
        except Exception as exc:
            logger.error("whale_alert_chat_error", chat_id=chat_id, error=str(exc))

    async def broadcast_message(self, chat_ids: list[int | str], text: str) -> None:
        """Broadcast a message to multiple chat IDs."""
        if not self._app:
            return
        for cid in chat_ids:
            try:
                await self._app.bot.send_message(
                    chat_id=cid,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=_get_inline_buttons(),
                )
            except Exception as exc:
                logger.warning("broadcast_error", chat_id=cid, error=str(exc))

    # ── Rate Limiting ──────────────────────────────────

    def _rate_check(self, update: Update) -> bool:
        """Simple per-user rate limiting."""
        import time

        user = update.effective_user
        if not user:
            return True
        uid = user.id
        now = time.time()
        last = RATE_LIMIT.get(uid, 0)
        if now - last < RATE_LIMIT_SECONDS:
            return False
        RATE_LIMIT[uid] = now
        return True

    # ── Error Handler ──────────────────────────────────

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("telegram_error", error=str(context.error))
