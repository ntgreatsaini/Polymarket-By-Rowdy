"""Premium Telegram message formatting for signals and alerts."""

from __future__ import annotations

from typing import Any

from src.config.settings import get_settings
from src.signals.generator import TradeSignal
from src.whales.tracker import WhaleAlert


def get_branding_footer() -> str:
    settings = get_settings()
    return (
        "\n━━━━━━━━━━━━━━\n"
        "🔥 Support Us By Follow\n\n"
        f"📢 TG:\n{settings.telegram_channel_link}\n\n"
        f"🐦 X:\n{settings.x_profile_link}\n"
        "━━━━━━━━━━━━━━"
    )


def format_signal(signal: TradeSignal) -> str:
    """Format a trade signal as a premium Telegram message."""
    confidence_emoji = _confidence_emoji(signal.confidence_score)
    risk_emoji = _risk_emoji(signal.risk_level)

    msg = (
        f"🚨 HIGH-CONFIDENCE SIGNAL\n\n"
        f"📊 *Market:*\n{_escape_md(signal.market_title)}\n\n"
        f"📈 *Current Probability:*\n{signal.yes_probability:.0%}\n\n"
        f"🧠 *AI Estimated Probability:*\n{signal.ai_probability:.0%}\n\n"
        f"🔥 *Expected Edge:*\n{signal.expected_edge:+.1f}%\n\n"
        f"{confidence_emoji} *Confidence:*\n{signal.confidence_score}/100\n\n"
        f"💧 *Liquidity:*\n{signal.liquidity_rating}\n\n"
        f"{risk_emoji} *Risk:*\n{signal.risk_level.replace('_', ' ').title()}\n\n"
        f"📰 *Reasoning:*\n{_escape_md(signal.ai_reasoning)}\n\n"
        f"📰 *News:*\n{_escape_md(signal.news_summary)}\n\n"
        f"📊 *Sentiment:*\n{_escape_md(signal.sentiment_summary)}\n\n"
        f"🐋 *Whale Activity:*\n{_escape_md(signal.whale_summary)}\n\n"
        f"💡 *Suggested Entry:*\n{_escape_md(signal.suggested_entry)}\n\n"
        f"🎯 *Suggested Exit:*\n{_escape_md(signal.suggested_exit)}\n\n"
        f"⏳ *Time Horizon:*\n{_escape_md(signal.time_horizon)}"
    )

    msg += get_branding_footer()
    return msg


def format_signal_compact(signal: TradeSignal) -> str:
    """Shorter format for quick alerts."""
    direction_emoji = "🟢" if signal.direction == "YES" else "🔴"
    return (
        f"{direction_emoji} *{signal.direction}* | "
        f"{_escape_md(signal.market_title[:80])}\n"
        f"Market: {signal.yes_probability:.0%} → AI: {signal.ai_probability:.0%} "
        f"(Edge: {signal.expected_edge:+.1f}%) "
        f"| Conf: {signal.confidence_score}/100"
    )


def format_whale_alert(alert: WhaleAlert) -> str:
    """Format a whale alert message."""
    side_emoji = "🟢" if alert.side == "BUY" else "🔴"
    msg = (
        f"🐋 WHALE ALERT\n\n"
        f"{side_emoji} *{alert.side}* — ${alert.amount:,.0f}\n\n"
        f"📊 *Market:*\n{_escape_md(alert.market_question or alert.market_id)}\n\n"
        f"💰 *Price:* {alert.price:.2%}\n"
        f"🧠 *Smart Money Score:* {alert.smart_money_score:.0%}\n"
        f"📋 *Type:* {alert.alert_type.replace('_', ' ').title()}"
    )
    msg += get_branding_footer()
    return msg


def format_market_info(market: dict[str, Any]) -> str:
    """Format market information for /market command."""
    msg = (
        f"📊 *Market Info*\n\n"
        f"❓ *Question:*\n{_escape_md(market.get('question', 'N/A'))}\n\n"
        f"📈 *YES Price:* {float(market.get('yes_price', 0)):.0%}\n"
        f"📉 *NO Price:* {float(market.get('no_price', 0)):.0%}\n"
        f"💰 *Volume:* ${float(market.get('volume', 0)):,.0f}\n"
        f"💧 *Liquidity:* ${float(market.get('liquidity', 0)):,.0f}\n"
        f"📁 *Category:* {market.get('category', 'other').title()}\n"
        f"🔗 *ID:* `{market.get('condition_id', 'N/A')}`"
    )
    msg += get_branding_footer()
    return msg


def format_trending(markets: list[dict[str, Any]], title: str = "🔥 Trending Markets") -> str:
    """Format a list of trending markets."""
    if not markets:
        return f"{title}\n\nNo trending markets found."

    lines = [f"{title}\n"]
    for i, m in enumerate(markets[:10], 1):
        q = _escape_md(m.get("question", "N/A")[:60])
        price = float(m.get("yes_price", 0))
        vol = float(m.get("volume", 0))
        lines.append(f"{i}\\. {q}\n   YES: {price:.0%} | Vol: ${vol:,.0f}")

    result = "\n".join(lines)
    result += get_branding_footer()
    return result


def format_performance(metrics: dict[str, Any]) -> str:
    """Format performance tracking metrics."""
    msg = (
        f"📊 *Performance Tracker*\n\n"
        f"📈 *Win Rate:* {metrics.get('win_rate', 0):.1%}\n"
        f"💰 *Total ROI:* {metrics.get('total_roi', 0):+.1%}\n"
        f"📊 *Total Signals:* {metrics.get('total_signals', 0)}\n"
        f"✅ *Wins:* {metrics.get('wins', 0)}\n"
        f"❌ *Losses:* {metrics.get('losses', 0)}\n"
        f"🎯 *Avg Confidence:* {metrics.get('avg_confidence', 0):.0f}/100\n\n"
        f"🏆 *Best Category:* {metrics.get('best_category', 'N/A')}\n"
        f"📉 *Worst Category:* {metrics.get('worst_category', 'N/A')}"
    )
    msg += get_branding_footer()
    return msg


def format_help() -> str:
    """Format help message with all available commands."""
    return (
        "🤖 *Polymarket Intelligence Bot*\n\n"
        "*Available Commands:*\n\n"
        "📊 *Market Analysis*\n"
        "/signals — Latest trade signals\n"
        "/highconfidence — High\\-confidence signals only\n"
        "/market _\\[name\\]_ — Search & analyze a market\n"
        "/trending — Trending markets\n"
        "/top — Top markets by volume\n\n"
        "📁 *Categories*\n"
        "/crypto — Crypto market signals\n"
        "/sports — Sports market signals\n"
        "/politics — Politics market signals\n"
        "/economy — Economy & macro signals\n\n"
        "🐋 *Whale Tracking*\n"
        "/whales — Recent whale activity\n\n"
        "📈 *Portfolio & Performance*\n"
        "/portfolio — Your signal portfolio\n"
        "/performance — Bot performance metrics\n\n"
        "⚙️ *Settings*\n"
        "/subscribe — Subscribe to alerts\n"
        "/unsubscribe — Unsubscribe from alerts\n\n"
        "/help — Show this message"
        + get_branding_footer()
    )


def format_start() -> str:
    """Format welcome message."""
    return (
        "🚀 *Welcome to Polymarket Intelligence Bot\\!*\n\n"
        "I analyze prediction markets using AI, sentiment analysis, "
        "whale tracking, and real\\-world data to generate "
        "high\\-confidence trade signals\\.\n\n"
        "Use /help to see all available commands\\.\n"
        "Use /subscribe to receive automatic alerts\\."
        + get_branding_footer()
    )


def _escape_md(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    special = r"_*[]()~`>#+-=|{}.!"
    result = ""
    for ch in text:
        if ch in special:
            result += f"\\{ch}"
        else:
            result += ch
    return result


def _confidence_emoji(score: int) -> str:
    if score >= 80:
        return "🎯"
    elif score >= 60:
        return "🔵"
    return "⚪"


def _risk_emoji(risk: str) -> str:
    mapping = {
        "low": "🟢",
        "medium": "⚠️",
        "high": "🔴",
        "very_high": "🚨",
    }
    return mapping.get(risk, "⚠️")
