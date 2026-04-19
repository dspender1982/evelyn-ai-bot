"""
AI Stock Picker
===============
Automatically researches and picks the best stocks to buy using:
1. News sentiment (Yahoo Finance RSS)
2. Price trend analysis (momentum, moving average)

Two modes available from the dashboard:
- Manual mode: you pick stocks yourself
- AI mode: bot picks automatically, you set how many

All picks are logged and emailed so you always know what and why.
"""

import logging
import urllib.request
import xml.etree.ElementTree as ET
import json
import os as _os
_IN_DOCKER = _os.path.exists("/.dockerenv") or _os.environ.get("IN_DOCKER")
DATA_DIR   = "/app/data" if _IN_DOCKER else _os.path.dirname(_os.path.abspath(__file__))
from datetime import datetime
from pathlib import Path

log = logging.getLogger()

# ── Candidate stocks the AI considers ────────────────────────────
# A broad universe of liquid, well-known stocks
CANDIDATE_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "PG", "MA", "HD", "CVX",
    "MRK", "ABBV", "PEP", "KO", "COST", "AVGO", "MCD", "CSCO", "ACN",
    "LIN", "TMO", "ABT", "DHR", "VZ", "ADBE", "NFLX", "INTC", "AMD",
    "CRM", "QCOM", "TXN", "NEE", "PM", "RTX", "HON", "UPS", "SBUX",
    "SPY", "QQQ", "DIA", "IWM", "VTI"
]

POSITIVE_WORDS = [
    "beat", "beats", "record", "growth", "profit", "surge", "rally",
    "upgrade", "bullish", "strong", "gains", "revenue", "dividend",
    "expansion", "partnership", "innovation", "outperform", "raised",
    "buy", "positive", "upside", "momentum", "breakout", "high"
]
NEGATIVE_WORDS = [
    "loss", "losses", "crash", "drop", "fell", "decline", "lawsuit",
    "downgrade", "bearish", "miss", "misses", "cut", "layoff", "layoffs",
    "recall", "fraud", "investigation", "warning", "debt", "risk",
    "bankruptcy", "sell-off", "underperform", "lowered", "concern",
    "weak", "negative", "downside", "selloff", "short"
]


def fetch_price_data(ticker):
    """Fetch recent price data from Yahoo Finance spark API."""
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/spark"
               f"?symbols={ticker}&range=1mo&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = json.loads(resp.read())
        spark  = raw.get("spark", {}).get("result") or []
        if not spark:
            return None
        resp_d = (spark[0].get("response") or [{}])[0]
        meta   = resp_d.get("meta", {})
        closes = resp_d.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [c for c in closes if c is not None]
        if not closes:
            return None
        return {
            "ticker":        ticker,
            "current_price": round(meta.get("regularMarketPrice", closes[-1]), 2),
            "prev_close":    round(meta.get("chartPreviousClose", closes[-2] if len(closes) > 1 else closes[-1]), 2),
            "closes":        closes,
            "high_52w":      round(meta.get("fiftyTwoWeekHigh", max(closes)), 2),
            "low_52w":       round(meta.get("fiftyTwoWeekLow",  min(closes)), 2),
        }
    except Exception as e:
        log.warning(f"[AI] Price fetch failed for {ticker}: {e}")
        return None


def score_price_trend(price_data):
    """
    Score a stock's price trend.
    Returns a score between -5 and +5.
    Positive = uptrend, Negative = downtrend.
    """
    if not price_data or len(price_data["closes"]) < 5:
        return 0, "insufficient data"

    closes  = price_data["closes"]
    current = price_data["current_price"]
    score   = 0
    reasons = []

    # 1. Short term momentum (5 day)
    if len(closes) >= 5:
        five_day_ago = closes[-5]
        pct_5d = ((current - five_day_ago) / five_day_ago) * 100
        if pct_5d > 3:
            score += 2
            reasons.append(f"5d +{pct_5d:.1f}%")
        elif pct_5d > 0:
            score += 1
            reasons.append(f"5d +{pct_5d:.1f}%")
        elif pct_5d < -3:
            score -= 2
            reasons.append(f"5d {pct_5d:.1f}%")
        else:
            score -= 1
            reasons.append(f"5d {pct_5d:.1f}%")

    # 2. Medium term momentum (20 day)
    if len(closes) >= 20:
        twenty_day_ago = closes[-20]
        pct_20d = ((current - twenty_day_ago) / twenty_day_ago) * 100
        if pct_20d > 5:
            score += 2
            reasons.append(f"20d +{pct_20d:.1f}%")
        elif pct_20d > 0:
            score += 1
            reasons.append(f"20d +{pct_20d:.1f}%")
        elif pct_20d < -5:
            score -= 2
            reasons.append(f"20d {pct_20d:.1f}%")
        else:
            score -= 1
            reasons.append(f"20d {pct_20d:.1f}%")

    # 3. Price vs 52 week range
    week52_range = price_data["high_52w"] - price_data["low_52w"]
    if week52_range > 0:
        position = (current - price_data["low_52w"]) / week52_range
        if position > 0.7:
            score += 1
            reasons.append(f"near 52w high ({position*100:.0f}%)")
        elif position < 0.3:
            score -= 1
            reasons.append(f"near 52w low ({position*100:.0f}%)")

    return max(-5, min(5, score)), ", ".join(reasons)


def fetch_news_score(ticker):
    """Fetch and score news sentiment for a ticker."""
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_data = resp.read()
        root      = ET.fromstring(xml_data)
        headlines = []
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title", "")
            if title:
                headlines.append(title)

        score = 0
        for title in headlines:
            text = title.lower()
            for w in POSITIVE_WORDS:
                if w in text:
                    score += 1
            for w in NEGATIVE_WORDS:
                if w in text:
                    score -= 1

        return max(-5, min(5, score)), headlines[:3]
    except Exception as e:
        log.warning(f"[AI] News fetch failed for {ticker}: {e}")
        return 0, []


def research_candidate(ticker):
    """
    Fully research a candidate stock.
    Returns a dict with combined score and reasoning.
    """
    log.info(f"[AI] Researching {ticker}...")

    price_data                   = fetch_price_data(ticker)
    trend_score, trend_reason    = score_price_trend(price_data)
    news_score,  headlines       = fetch_news_score(ticker)
    combined_score               = trend_score + news_score

    return {
        "ticker":         ticker,
        "combined_score": combined_score,
        "trend_score":    trend_score,
        "news_score":     news_score,
        "trend_reason":   trend_reason,
        "top_headlines":  headlines,
        "price":          price_data["current_price"] if price_data else None,
        "timestamp":      datetime.now().isoformat()
    }


def pick_stocks(num_stocks=5, exclude=None):
    """
    Research all candidates and return the top N picks.
    exclude: list of tickers to skip (e.g. already held)
    """
    exclude   = exclude or []
    results   = []
    candidates = [t for t in CANDIDATE_UNIVERSE if t not in exclude]

    log.info(f"[AI] Researching {len(candidates)} candidates to pick top {num_stocks}...")

    for ticker in candidates:
        try:
            result = research_candidate(ticker)
            results.append(result)
        except Exception as e:
            log.warning(f"[AI] Skipping {ticker}: {e}")

    # Sort by combined score descending
    results.sort(key=lambda x: x["combined_score"], reverse=True)
    top_picks = results[:num_stocks]

    log.info(f"[AI] Top {num_stocks} picks: {[p['ticker'] for p in top_picks]}")
    return top_picks


def format_picks_email(picks, dollar_amount_each):
    """Format a nice email summary of AI picks."""
    lines = [
        "AI Stock Picker — New Selections",
        "=" * 40,
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Buying ${dollar_amount_each} of each pick",
        "",
        "Selected stocks:",
        "-" * 40,
    ]
    for p in picks:
        lines += [
            f"{p['ticker']} — Score: {p['combined_score']:+d} "
            f"(trend: {p['trend_score']:+d}, news: {p['news_score']:+d})",
            f"  Price    : ${p['price']}" if p['price'] else "  Price: unknown",
            f"  Trend    : {p['trend_reason'] or 'n/a'}",
            f"  News     : {p['top_headlines'][0] if p['top_headlines'] else 'no headlines'}",
            "",
        ]
    lines += [
        "=" * 40,
        "This is an automated message from your Evelyn AI picker.",
        "Always review picks before going live with real money."
    ]
    return "\n".join(lines)


def save_picks(picks, path=_os.path.join(DATA_DIR, "ai_picks.json")):
    """Save current AI picks to a JSON file."""
    with open(path, "w") as f:
        json.dump({
            "picks":     picks,
            "timestamp": datetime.now().isoformat()
        }, f, indent=2)


def load_picks(path=_os.path.join(DATA_DIR, "ai_picks.json")):
    """Load last saved AI picks."""
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return None
