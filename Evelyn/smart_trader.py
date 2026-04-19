"""
Smart Trader Module
===================
Adds three intelligent features to the Evelyn:

1. PROFIT TARGET — auto-sell when a stock gains enough (e.g. +20%)
2. STOP-LOSS     — auto-sell when a stock drops too much (e.g. -10%)
3. NEWS RESEARCH — uses Yahoo Finance RSS + basic sentiment to score
                   stocks before buying (skips stocks with bad news)

All decisions are logged and emailed so you stay in control.
"""

import logging
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

log = logging.getLogger()

# ── Config (overridden by bot_config.json via server.py) ──────────
PROFIT_TARGET_PCT  = 20.0   # Sell if gain >= this %
STOP_LOSS_PCT      = 10.0   # Sell if loss >= this %
NEWS_CHECK_ENABLED = True   # Skip buys on bad news sentiment
NEWS_MIN_SCORE     = -2     # Minimum sentiment score to allow buy (-5 worst, +5 best)

# ── Sentiment keywords ────────────────────────────────────────────
POSITIVE_WORDS = [
    "beat", "beats", "record", "growth", "profit", "surge", "rally",
    "upgrade", "bullish", "strong", "gains", "revenue", "dividend",
    "expansion", "partnership", "innovation", "outperform", "raised"
]
NEGATIVE_WORDS = [
    "loss", "losses", "crash", "drop", "fell", "decline", "lawsuit",
    "downgrade", "bearish", "miss", "misses", "cut", "layoff", "layoffs",
    "recall", "fraud", "investigation", "warning", "debt", "risk",
    "bankruptcy", "sell-off", "underperform", "lowered", "concern"
]

# ═══════════════════════════════════════════════════════════════════
#   NEWS RESEARCH
# ═══════════════════════════════════════════════════════════════════

def fetch_news_headlines(ticker: str, max_items: int = 10) -> list:
    """Fetch recent headlines for a ticker from Yahoo Finance RSS."""
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        headlines = []
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "")
            pub   = item.findtext("pubDate", "")
            if title:
                headlines.append({"title": title, "date": pub})
        return headlines
    except Exception as e:
        log.warning(f"[NEWS] Could not fetch headlines for {ticker}: {e}")
        return []


def score_sentiment(headlines: list) -> tuple:
    """
    Score sentiment from headlines.
    Returns (score: int, summary: str)
    score > 0 = positive, < 0 = negative, 0 = neutral
    """
    score = 0
    hits  = []
    for item in headlines:
        text = item["title"].lower()
        for w in POSITIVE_WORDS:
            if w in text:
                score += 1
                hits.append(f"+{w}")
        for w in NEGATIVE_WORDS:
            if w in text:
                score -= 1
                hits.append(f"-{w}")

    if score >= 3:
        mood = "positive"
    elif score <= -3:
        mood = "negative"
    else:
        mood = "neutral"

    summary = f"Score: {score:+d} ({mood}). Signals: {', '.join(hits[:8]) if hits else 'none'}"
    return score, summary


def research_stock(ticker: str) -> dict:
    """
    Research a stock before buying.
    Returns dict with: ticker, score, mood, headlines, recommendation
    """
    log.info(f"[NEWS] Researching {ticker}...")
    headlines = fetch_news_headlines(ticker)

    if not headlines:
        return {
            "ticker": ticker, "score": 0, "mood": "unknown",
            "headlines": [], "recommendation": "neutral",
            "reason": "No news found — proceeding with caution"
        }

    score, summary = score_sentiment(headlines)
    log.info(f"[NEWS] {ticker} sentiment: {summary}")

    if score >= NEWS_MIN_SCORE:
        rec    = "buy"
        reason = f"Sentiment OK ({summary})"
    else:
        rec    = "skip"
        reason = f"Negative sentiment ({summary}) — skipping buy"

    return {
        "ticker":         ticker,
        "score":          score,
        "mood":           "positive" if score > 0 else "negative" if score < 0 else "neutral",
        "headlines":      [h["title"] for h in headlines[:5]],
        "recommendation": rec,
        "reason":         reason
    }


def should_buy(ticker: str) -> tuple:
    """
    Returns (True/False, reason string).
    True = go ahead and buy. False = skip this cycle.
    """
    if not NEWS_CHECK_ENABLED:
        return True, "News check disabled"

    result = research_stock(ticker)
    allow  = result["recommendation"] == "buy"

    if not allow:
        log.warning(f"[NEWS] Skipping {ticker}: {result['reason']}")
    else:
        log.info(f"[NEWS] {ticker} approved: {result['reason']}")

    return allow, result["reason"]


# ═══════════════════════════════════════════════════════════════════
#   PROFIT TARGET & STOP-LOSS MONITOR
# ═══════════════════════════════════════════════════════════════════

def check_exit_conditions(holdings: dict, rh_module) -> list:
    """
    Check all holdings for profit target or stop-loss triggers.
    Returns list of sell actions taken.

    holdings: output of rh.account.build_holdings()
    rh_module: the robin_stocks.robinhood module
    """
    actions = []

    for ticker, data in holdings.items():
        try:
            qty       = float(data.get("quantity", 0))
            avg_buy   = float(data.get("average_buy_price", 0))
            cur_price = float(data.get("price", 0))

            if qty <= 0 or avg_buy <= 0 or cur_price <= 0:
                continue

            pct_change = ((cur_price - avg_buy) / avg_buy) * 100

            action = None
            reason = None

            if pct_change >= PROFIT_TARGET_PCT:
                action = "sell_profit"
                reason = (f"Profit target hit: {pct_change:+.1f}% "
                          f"(target +{PROFIT_TARGET_PCT}%)")

            elif pct_change <= -STOP_LOSS_PCT:
                action = "sell_stoploss"
                reason = (f"Stop-loss triggered: {pct_change:+.1f}% "
                          f"(limit -{STOP_LOSS_PCT}%)")

            if action:
                log.info(f"[EXIT] {ticker}: {reason} — selling {qty:.4f} shares")
                result = execute_sell(ticker, qty, cur_price, reason, rh_module)
                actions.append({
                    "ticker":     ticker,
                    "action":     action,
                    "reason":     reason,
                    "qty":        qty,
                    "avg_buy":    avg_buy,
                    "sell_price": cur_price,
                    "pct_change": round(pct_change, 2),
                    "success":    result
                })
            else:
                log.info(
                    f"[MONITOR] {ticker}: {pct_change:+.1f}% "
                    f"(buy ${avg_buy:.2f} → now ${cur_price:.2f}) — holding"
                )

        except Exception as e:
            log.error(f"[EXIT] Error checking {ticker}: {e}")

    return actions


def execute_sell(ticker: str, qty: float, price: float, reason: str, rh_module) -> bool:
    """Place a market sell order for all shares of a ticker."""
    try:
        order = rh_module.orders.order_sell_fractional_by_quantity(
            ticker,
            qty,
            timeInForce="gfd",
            extendedHours=False
        )
        log.info(f"[SELL] {ticker} sell order placed: {order}")
        return True
    except Exception as e:
        log.error(f"[SELL] Failed to sell {ticker}: {e}")
        return False


def format_exit_email(actions: list) -> str:
    """Format a summary email for exit actions taken."""
    if not actions:
        return ""
    lines = ["Evelyn — Auto-Sell Report", "=" * 40]
    for a in actions:
        emoji = "PROFIT TARGET" if a["action"] == "sell_profit" else "STOP-LOSS"
        lines += [
            f"[{emoji}] {a['ticker']}",
            f"  Change    : {a['pct_change']:+.2f}%",
            f"  Avg buy   : ${a['avg_buy']:.2f}",
            f"  Sold at   : ${a['sell_price']:.2f}",
            f"  Qty       : {a['qty']:.4f} shares",
            f"  Reason    : {a['reason']}",
            f"  Status    : {'SUCCESS' if a['success'] else 'FAILED'}",
            ""
        ]
    lines.append("=" * 40)
    lines.append("This is an automated message from your Evelyn.")
    return "\n".join(lines)
