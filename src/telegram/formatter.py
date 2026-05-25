"""Premium Telegram message formatting for signals and alerts."""

from __future__ import annotations

from typing import Any

from src.config.settings import get_settings
from src.signals.generator import CrossMarketComparison, TradeSignal
from src.whales.tracker import WhaleAlert


def get_branding_footer() -> str:
    settings = get_settings()
    tg_link = _escape_md(settings.telegram_channel_link)
    x_link = _escape_md(settings.x_profile_link)
    return (
        "\n━━━━━━━━━━━━━━\n"
        "🔥 Support Us By Follow\n\n"
        f"📢 TG:\n{tg_link}\n\n"
        f"🐦 X:\n{x_link}\n"
        "━━━━━━━━━━━━━━"
    )


def format_signal(signal: TradeSignal) -> str:
    """Format a trade signal as a premium Telegram message matching POLY AI SIGNAL format."""
    yes_pct = signal.yes_probability * 100
    no_pct = signal.no_probability * 100
    ai_pct = signal.ai_probability * 100
    trade_price = signal.yes_probability if signal.direction == "YES" else signal.no_probability
    momentum_emoji = {"bullish": "📈", "bearish": "📉"}.get(signal.momentum_trend, "➡️")

    msg = "🚨 *POLY AI SIGNAL*\n\n"

    # Market title
    msg += f"🎯 *Market:*\n{_escape_md(signal.market_title)}\n\n"

    # Trade link
    if signal.trade_url:
        msg += f"🔗 *Trade Link:*\n{_escape_md(signal.trade_url)}\n\n"

    # Market odds
    msg += (
        "📊 *Market Odds:*\n"
        f"🟢 YES: {_escape_md(f'{yes_pct:.0f}')}%\n"
        f"🔴 NO: {_escape_md(f'{no_pct:.0f}')}%\n\n"
    )

    # AI probability
    msg += f"🧠 *AI Probability:*\n{_escape_md(f'{ai_pct:.0f}')}%\n\n"

    # Expected edge
    msg += f"🔥 *Expected Edge:*\n{_escape_md(f'{signal.expected_edge:+.0f}')}%\n\n"

    # Trade setup
    entry_price = trade_price * 100
    target_price = ai_pct
    msg += (
        "💰 *Trade Setup:*\n"
        f"{signal.direction} buy @ {_escape_md(f'{entry_price:.0f}')}%\n"
        f"🎯 Target: {_escape_md(f'{target_price:.0f}')}%\\+\n\n"
    )

    # Expiry
    if signal.expiry_date:
        msg += f"⏳ *Expiry:*\n{_escape_md(signal.expiry_date)}\n\n"
    else:
        msg += f"⏳ *Time Horizon:*\n{_escape_md(signal.time_horizon)}\n\n"

    # Momentum
    msg += f"{momentum_emoji} *Momentum:*\n{_escape_md(signal.momentum_trend.title())} short\\-term\n\n"

    # Whale flow
    msg += f"🐋 *Whale Flow:*\n{_escape_md(signal.whale_summary)}\n\n"

    # Cross-market comparison
    if signal.cross_market.has_data:
        msg += "🌍 *Cross\\-Market Comparison:*\n"
        msg += f"Polymarket: {_escape_md(f'{yes_pct:.0f}')}%\n"
        for venue in signal.cross_market.other_venues:
            v_pct = venue.probability * 100
            msg += f"{_escape_md(venue.venue)}: {_escape_md(f'{v_pct:.0f}')}%\n"
        msg += "\n"

    # Sentiment
    rb = signal.risk_score_breakdown
    sentiment_dir = rb.get("sentiment_direction", signal.sentiment_summary.split()[0] if signal.sentiment_summary else "Neutral")
    msg += f"📡 *Sentiment:*\n{_escape_md(sentiment_dir)}\n\n"

    # AI thesis
    msg += f"📰 *AI Thesis:*\n{_escape_md(signal.ai_reasoning)}\n\n"

    # Risk
    risk_emoji = _risk_emoji(signal.risk_level)
    msg += f"{risk_emoji} *Risk:*\n{_escape_md(signal.risk_level.replace('_', ' ').title())}\n\n"

    # Confidence
    msg += f"🎯 *Confidence:*\n{signal.confidence_score}/100\n\n"

    # Signal quality
    msg += f"⭐ *Signal Quality:*\n{_escape_md(signal.signal_quality)}\n\n"

    # Potential ROI
    msg += f"💎 *Potential ROI:*\n{_escape_md(f'+{signal.potential_roi:.0f}')}%\n"

    msg += get_branding_footer()
    return msg


def format_signal_compact(signal: TradeSignal) -> str:
    """Shorter format for quick alerts."""
    direction_emoji = "🟢" if signal.direction == "YES" else "🔴"
    win_pct = signal.win_probability * 100
    ev_emoji = "✅" if signal.expected_value > 0 else "⚠️"
    msg = (
        f"{direction_emoji} *{signal.direction}* \\| "
        f"{_escape_md(signal.market_title[:80])}\n"
        f"🎯 Win: {_escape_md(f'{win_pct:.0f}')}% \\| "
        f"Edge: {_escape_md(f'{signal.expected_edge:+.1f}')}% \\| "
        f"{ev_emoji} EV: {_escape_md(f'{signal.expected_value:+.1f}')}%\n"
        f"Market: {signal.yes_probability:.0%} → AI: {signal.ai_probability:.0%} "
        f"\\| Conf: {signal.confidence_score}/100 \\| Risk: {signal.risk_level.replace('_', ' ').title()}"
    )
    if signal.trade_url:
        msg += f"\n🔗 {_escape_md(signal.trade_url)}"
    return msg


def format_whale_alert(alert: WhaleAlert) -> str:
    """Format a whale alert message."""
    side_emoji = "🟢" if alert.side == "BUY" else "🔴"
    msg = (
        f"🐋 WHALE ALERT\n\n"
        f"{side_emoji} *{alert.side}* — ${alert.amount:,.0f}\n\n"
        f"📊 *Market:*\n{_escape_md(alert.market_question or alert.market_id)}\n\n"
        f"💰 *Price:* {_escape_md(f'{alert.price:.2%}')}\n"
        f"🧠 *Smart Money Score:* {alert.smart_money_score:.0%}\n"
        f"📋 *Type:* {alert.alert_type.replace('_', ' ').title()}"
    )
    msg += get_branding_footer()
    return msg


def format_market_info(market: dict[str, Any]) -> str:
    """Format market information for /market command."""
    yes_price = float(market.get('yes_price', 0))
    no_price = float(market.get('no_price', 0))
    volume = float(market.get('volume', 0))
    liquidity = float(market.get('liquidity', 0))
    slug = market.get('slug', '')
    trade_url = f"https://polymarket.com/event/{slug}" if slug else ""

    msg = (
        f"📊 *Market Info*\n\n"
        f"❓ *Question:*\n{_escape_md(market.get('question', 'N/A'))}\n\n"
        f"📈 *YES Price:* {yes_price:.0%}\n"
        f"📉 *NO Price:* {no_price:.0%}\n"
        f"💰 *Volume:* ${volume:,.0f}\n"
        f"💧 *Liquidity:* ${liquidity:,.0f}\n"
        f"📁 *Category:* {market.get('category', 'other').replace('_', ' ').title()}\n"
    )

    # Quick stats
    if yes_price > 0 and yes_price < 1:
        liq_rating = "Very High" if liquidity >= 100_000 else "High" if liquidity >= 50_000 else "Medium" if liquidity >= 10_000 else "Low"
        msg += (
            f"\n📊 *Quick Stats:*\n"
            f"  💧 Liquidity Rating: {liq_rating}\n"
            f"  📊 YES implies {yes_price:.0%} chance\n"
            f"  📊 NO implies {no_price:.0%} chance\n"
        )

    if trade_url:
        msg += f"\n🔗 *Trade Now:*\n{_escape_md(trade_url)}\n"

    msg += f"🔗 *ID:* `{market.get('condition_id', 'N/A')}`"
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
        slug = m.get("slug", "")
        trade_link = f"https://polymarket.com/event/{slug}" if slug else ""
        line = f"{i}\\. {q}\n   YES: {price:.0%} \\| Vol: ${vol:,.0f}"
        if trade_link:
            line += f"\n   🔗 {_escape_md(trade_link)}"
        lines.append(line)

    result = "\n".join(lines)
    result += get_branding_footer()
    return result


def format_performance(metrics: dict[str, Any]) -> str:
    """Format performance tracking metrics."""
    msg = (
        f"📊 *Performance Tracker*\n\n"
        f"📈 *Win Rate:* {_escape_md(f"{metrics.get('win_rate', 0):.1%}")}\n"
        f"💰 *Total ROI:* {_escape_md(f"{metrics.get('total_roi', 0):+.1%}")}\n"
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
        "🐋 *Whale Tracking & Smart Money*\n"
        "/whales — Whale activity \\(CLOB \\+ OddPool\\)\n"
        "/smartmoney — Merlin smart money & insiders\n"
        "/arbitrage — Cross\\-venue arbitrage \\(OddPool\\)\n\n"
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
