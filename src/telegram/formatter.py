"""Premium Telegram message formatting for signals and alerts."""

from __future__ import annotations

from typing import Any

from src.config.settings import get_settings
from src.signals.generator import TradeSignal
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
    """Format a trade signal as a premium Telegram message."""
    confidence_emoji = _confidence_emoji(signal.confidence_score)
    risk_emoji = _risk_emoji(signal.risk_level)
    consensus_tag = ""
    if signal.ai_models_used > 1:
        if signal.ai_models_agree:
            consensus_tag = f" \\[{signal.ai_models_used} AI AGREE\\]"
        else:
            consensus_tag = f" \\[{signal.ai_models_used} AI SPLIT\\]"
    momentum_emoji = {"bullish": "📈", "bearish": "📉"}.get(signal.momentum_trend, "➡️")
    direction_emoji = "🟢" if signal.direction == "YES" else "🔴"
    win_pct = signal.win_probability * 100
    ev_emoji = "✅" if signal.expected_value > 0 else "⚠️"

    msg = (
        f"🚨 HIGH\\-CONFIDENCE SIGNAL{consensus_tag}\n\n"
        f"📊 *Market:*\n{_escape_md(signal.market_title)}\n\n"
        f"{direction_emoji} *Direction:* {signal.direction}\n\n"
    )

    # Win probability & trade stats — the key section
    msg += (
        "━━━ 🏆 WIN ANALYSIS ━━━\n"
        f"🎯 *Win Probability:* {_escape_md(f'{win_pct:.1f}')}%\n"
        f"📈 *Current Market Price:* {signal.yes_probability:.0%} YES \\| {signal.no_probability:.0%} NO\n"
        f"🧠 *AI Estimated Probability:* {signal.ai_probability:.0%}\n"
        f"🔥 *Expected Edge:* {_escape_md(f'{signal.expected_edge:+.1f}')}%\n"
        f"{ev_emoji} *Expected Value \\(EV\\):* {_escape_md(f'{signal.expected_value:+.1f}')}%\n"
        f"💰 *Kelly Bet Size:* {_escape_md(f'{signal.kelly_bet_size:.1%}')} of bankroll\n"
        f"{confidence_emoji} *Confidence:* {signal.confidence_score}/100\n\n"
    )

    # Risk analysis section
    rb = signal.risk_score_breakdown
    msg += (
        "━━━ ⚠️ RISK ANALYSIS ━━━\n"
        f"{risk_emoji} *Overall Risk:* {signal.risk_level.replace('_', ' ').title()}\n"
        f"💧 *Liquidity:* {_escape_md(signal.liquidity_rating)}"
        f" \\(Risk: {_escape_md(rb.get('liquidity_risk', 'N/A'))}\\)\n"
        f"📊 *Volume Risk:* {_escape_md(rb.get('volume_risk', 'N/A'))}\n"
        f"📈 *Volatility:* {_escape_md(signal.volatility_rating)}"
        f" \\({_escape_md(rb.get('volatility', 'N/A'))}\\)\n"
        f"{momentum_emoji} *Momentum:* {_escape_md(signal.momentum_trend.title())}\n"
        f"🐋 *Whale Alignment:* {_escape_md(rb.get('whale_alignment', 'N/A'))}\n"
        f"📰 *Sentiment:* {_escape_md(rb.get('sentiment_direction', 'N/A'))}\n"
        f"🤖 *AI Consensus:* {_escape_md(rb.get('ai_consensus', 'N/A'))}\n\n"
    )

    # AI reasoning & data
    msg += (
        "━━━ 🧠 AI ANALYSIS ━━━\n"
        f"📰 *Reasoning:*\n{_escape_md(signal.ai_reasoning)}\n\n"
        f"📰 *News:*\n{_escape_md(signal.news_summary)}\n\n"
        f"📊 *Sentiment:*\n{_escape_md(signal.sentiment_summary)}\n\n"
        f"🐋 *Whale Activity:*\n{_escape_md(signal.whale_summary)}\n\n"
    )

    # Trade execution section
    msg += (
        "━━━ 💰 TRADE EXECUTION ━━━\n"
        f"💡 *Suggested Entry:* {_escape_md(signal.suggested_entry)}\n"
        f"🎯 *Suggested Exit:* {_escape_md(signal.suggested_exit)}\n"
        f"⏳ *Time Horizon:* {_escape_md(signal.time_horizon)}\n"
    )

    # Trade link
    if signal.trade_url:
        msg += f"\n🔗 *Trade Now:*\n{_escape_md(signal.trade_url)}\n"

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
