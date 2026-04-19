"""
Stock Advisor — Alert Only Mode
================================
Researches stocks and sends email recommendations but NEVER trades.
You decide what to buy or sell yourself in Robinhood.

Runs on a schedule and emails you:
- BUY alerts when a stock looks good
- SELL alerts when a held stock hits profit target or stop loss
- Weekly portfolio summary with recommendations
- AI-picked stock suggestions if AI mode is on
"""

import logging
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

log = logging.getLogger()


def build_buy_alert(ticker, price, news_score, trend_score, reasons, headlines):
    """Build a BUY recommendation email."""
    combined = news_score + trend_score
    strength = "STRONG BUY" if combined >= 5 else "BUY" if combined >= 2 else "WEAK BUY"

    lines = [
        f"BUY ALERT — {ticker}",
        "=" * 40,
        f"Recommendation : {strength}",
        f"Ticker         : {ticker}",
        f"Current Price  : ${price:.2f}" if price else "Current Price  : unavailable",
        f"Combined Score : {combined:+d}",
        f"  News score   : {news_score:+d}",
        f"  Trend score  : {trend_score:+d}",
        "",
        "Reasons:",
        reasons or "  No specific reasons found",
        "",
        "Recent headlines:",
    ]
    for h in (headlines or [])[:3]:
        lines.append(f"  • {h}")

    lines += [
        "",
        "=" * 40,
        "ACTION REQUIRED: Log into Robinhood and decide if you want to buy.",
        "This is a suggestion only — the bot will NOT trade automatically.",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    return f"Evelyn: {strength} — {ticker}", "\n".join(lines)


def build_sell_alert(ticker, qty, avg_buy, current_price, pct_change, reason):
    """Build a SELL recommendation email."""
    action = "TAKE PROFIT" if pct_change > 0 else "CUT LOSS"
    profit_loss = (current_price - avg_buy) * qty

    lines = [
        f"SELL ALERT — {ticker}",
        "=" * 40,
        f"Recommendation : {action}",
        f"Ticker         : {ticker}",
        f"Your avg buy   : ${avg_buy:.2f}",
        f"Current price  : ${current_price:.2f}",
        f"Change         : {pct_change:+.2f}%",
        f"Your shares    : {qty:.4f}",
        f"P&L if sold now: ${profit_loss:+.2f}",
        f"Reason         : {reason}",
        "",
        "=" * 40,
        "ACTION REQUIRED: Log into Robinhood and decide if you want to sell.",
        "This is a suggestion only — the bot will NOT trade automatically.",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    return f"Evelyn: {action} — {ticker} ({pct_change:+.1f}%)", "\n".join(lines)


def build_weekly_report(holdings, portfolio_value, day_change, buy_suggestions, sell_suggestions):
    """Build a weekly portfolio summary with recommendations."""
    lines = [
        "Weekly Portfolio Report",
        "=" * 40,
        f"Date           : {datetime.now().strftime('%Y-%m-%d')}",
        f"Portfolio value: ${portfolio_value:,.2f}",
        f"Day change     : ${day_change:+.2f}",
        "",
        "Your holdings:",
        "-" * 40,
    ]

    for ticker, data in (holdings or {}).items():
        qty   = float(data.get("quantity", 0))
        avg   = float(data.get("average_buy_price", 0))
        price = float(data.get("price", 0))
        val   = float(data.get("equity", 0))
        gain  = float(data.get("percent_change", 0))
        flag  = " *** CONSIDER SELLING" if gain > 20 else " * WATCH" if gain < -8 else ""
        lines.append(
            f"{ticker:<6} | {qty:.4f} shares | avg ${avg:.2f} | "
            f"now ${price:.2f} | ${val:.2f} | {gain:+.2f}%{flag}"
        )

    if sell_suggestions:
        lines += ["", "SELL SUGGESTIONS:", "-" * 40]
        for s in sell_suggestions:
            lines.append(f"  SELL {s['ticker']} — {s['reason']}")

    if buy_suggestions:
        lines += ["", "BUY SUGGESTIONS:", "-" * 40]
        for b in buy_suggestions:
            lines.append(f"  BUY {b['ticker']} — score {b['combined_score']:+d} — ${b['price']:.2f}" if b.get('price') else f"  BUY {b['ticker']} — score {b['combined_score']:+d}")

    lines += [
        "",
        "=" * 40,
        "These are suggestions only. Log into Robinhood to act on them.",
        "The bot will NOT trade automatically in Alert Only mode.",
    ]
    return "Evelyn: Weekly Portfolio Report", "\n".join(lines)


def build_ai_suggestions_email(picks, dollar_each):
    """Build an email with AI stock suggestions."""
    lines = [
        "AI Stock Suggestions",
        "=" * 40,
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Suggested investment: ~${dollar_each} each",
        "",
        "Top picks this cycle:",
        "-" * 40,
    ]
    for p in picks:
        lines += [
            f"{p['ticker']:<6} | Score: {p['combined_score']:+d} "
            f"(trend: {p['trend_score']:+d}, news: {p['news_score']:+d})"
            + (f" | ${p['price']:.2f}" if p.get('price') else ""),
            f"         Trend : {p['trend_reason'] or 'n/a'}",
            f"         News  : {p['top_headlines'][0] if p.get('top_headlines') else 'no headlines'}",
            "",
        ]
    lines += [
        "=" * 40,
        "These are AI suggestions only. Log into Robinhood to act on them.",
        "The bot will NOT trade automatically in Alert Only mode.",
        "",
        "Disclaimer: AI suggestions are based on simple news sentiment and",
        "price trends. Always do your own research before investing.",
    ]
    return "Evelyn: AI Stock Suggestions", "\n".join(lines)
