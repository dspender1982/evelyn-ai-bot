"""
Evelyn Monitors
===============
Background monitors that run on a schedule and send alerts:

1. Price Target    — email when a stock hits your set price
2. Earnings        — email 2 days before a stock reports earnings
3. Unusual Volume  — email when volume spikes 2x normal
4. Insider Trading — email when executives buy/sell their own stock
"""

import logging
import urllib.request
import json
from app_config import DATA_DIR, ensure_dirs
ensure_dirs()
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger()

MONITORS_FILE = str(DATA_DIR / 'monitors.json')

# ── Default monitors config ───────────────────────────────────────
DEFAULT_MONITORS = {
    "price_targets":    {},   # { "AAPL": {"target": 220.0, "direction": "above"} }
    "earnings_alerts":  True,
    "volume_alerts":    True,
    "volume_threshold": 2.0,  # x times average volume
    "insider_alerts":   True,
}

def load_monitors():
    if Path(MONITORS_FILE).exists():
        with open(MONITORS_FILE) as f:
            return {**DEFAULT_MONITORS, **json.load(f)}
    return DEFAULT_MONITORS.copy()

def save_monitors(m):
    with open(MONITORS_FILE, "w") as f:
        json.dump(m, f, indent=2)

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())

# ══════════════════════════════════════════════════════════════════
#   1. PRICE TARGET ALERTS
# ══════════════════════════════════════════════════════════════════

def set_price_target(ticker, target_price, direction="above"):
    """Set a price target alert. direction = 'above' or 'below'."""
    m = load_monitors()
    m["price_targets"][ticker.upper()] = {
        "target":    round(float(target_price), 2),
        "direction": direction,
        "set_at":    datetime.now().isoformat(),
        "triggered": False
    }
    save_monitors(m)
    log.info(f"[PRICE TARGET] Set: {ticker} {direction} ${target_price:.2f}")

def remove_price_target(ticker):
    m = load_monitors()
    m["price_targets"].pop(ticker.upper(), None)
    save_monitors(m)

def check_price_targets(send_email_fn):
    """Check all price targets and send alerts if hit."""
    m = load_monitors()
    targets = m.get("price_targets", {})
    if not targets:
        return

    triggered = []
    for ticker, cfg in list(targets.items()):
        if cfg.get("triggered"):
            continue
        try:
            data    = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d")
            meta    = data["chart"]["result"][0]["meta"]
            price   = meta.get("regularMarketPrice", 0)
            target  = cfg["target"]
            direction = cfg.get("direction", "above")

            hit = (direction == "above" and price >= target) or \
                  (direction == "below" and price <= target)

            if hit:
                log.info(f"[PRICE TARGET] {ticker} hit ${price:.2f} (target: {direction} ${target:.2f})")
                subject = f"Evelyn: Price Target Hit — {ticker} ${price:.2f}"
                body = f"""Price Target Alert — {ticker}
{'=' * 40}
Target    : {direction.upper()} ${target:.2f}
Current   : ${price:.2f}
Status    : TARGET HIT
Time      : {datetime.now().strftime('%Y-%m-%d %H:%M')}
{'=' * 40}
Log into Robinhood to review your position.
This is an alert only — Evelyn will not trade automatically."""
                send_email_fn(subject, body)
                # Mark as triggered so we don't spam
                m["price_targets"][ticker]["triggered"] = True
                triggered.append(ticker)
        except Exception as e:
            log.warning(f"[PRICE TARGET] Error checking {ticker}: {e}")

    if triggered:
        save_monitors(m)
    log.info(f"[PRICE TARGET] Checked {len(targets)} targets. Triggered: {triggered or 'none'}")

# ══════════════════════════════════════════════════════════════════
#   2. EARNINGS CALENDAR
# ══════════════════════════════════════════════════════════════════

def check_earnings_calendar(tickers, send_email_fn):
    """Check if any of your stocks report earnings in the next 3 days."""
    alerts = []
    for ticker in tickers:
        try:
            data   = fetch_json(f"https://query1.finance.yahoo.com/v11/finance/quoteSummary/{ticker}?modules=calendarEvents")
            events = data.get("quoteSummary", {}).get("result", [{}])[0]
            earnings_dates = events.get("calendarEvents", {}).get("earnings", {}).get("earningsDate", [])
            for ed in earnings_dates:
                ts   = ed.get("raw", 0)
                date = datetime.fromtimestamp(ts)
                days_away = (date.date() - datetime.now().date()).days
                if 0 <= days_away <= 3:
                    alerts.append({
                        "ticker": ticker,
                        "date":   date.strftime("%Y-%m-%d"),
                        "days":   days_away
                    })
                    log.info(f"[EARNINGS] {ticker} reports in {days_away} day(s) on {date.strftime('%Y-%m-%d')}")
        except Exception as e:
            log.warning(f"[EARNINGS] Error checking {ticker}: {e}")

    if alerts:
        lines = ["Earnings Calendar Alert", "=" * 40,
                 f"Date: {datetime.now().strftime('%Y-%m-%d')}", ""]
        for a in alerts:
            dow = "TODAY" if a["days"] == 0 else f"in {a['days']} day(s)"
            lines.append(f"{a['ticker']:<6} reports {dow} — {a['date']}")
        lines += ["", "=" * 40,
                  "Consider whether to hold or sell before earnings.",
                  "This is an alert only — Evelyn will not trade automatically."]
        send_email_fn("Evelyn: Earnings Alert — " + ", ".join(a["ticker"] for a in alerts),
                      "\n".join(lines))

# ══════════════════════════════════════════════════════════════════
#   3. UNUSUAL VOLUME ALERTS
# ══════════════════════════════════════════════════════════════════

def check_unusual_volume(tickers, threshold, send_email_fn):
    """Alert when a stock's volume is unusually high."""
    alerts = []
    for ticker in tickers:
        try:
            data   = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d")
            result = data["chart"]["result"][0]
            vols   = result["indicators"]["quote"][0].get("volume", [])
            vols   = [v for v in vols if v]
            if len(vols) < 5:
                continue
            avg_vol  = sum(vols[:-1]) / len(vols[:-1])
            curr_vol = vols[-1]
            ratio    = curr_vol / avg_vol if avg_vol else 1
            price    = result["meta"].get("regularMarketPrice", 0)
            pct      = ((price - result["meta"].get("chartPreviousClose", price)) /
                        result["meta"].get("chartPreviousClose", price) * 100) if result["meta"].get("chartPreviousClose") else 0

            if ratio >= threshold:
                alerts.append({
                    "ticker":   ticker,
                    "ratio":    round(ratio, 1),
                    "curr_vol": curr_vol,
                    "avg_vol":  round(avg_vol),
                    "price":    round(price, 2),
                    "pct":      round(pct, 2)
                })
                log.info(f"[VOLUME] {ticker} volume {ratio:.1f}x average!")
        except Exception as e:
            log.warning(f"[VOLUME] Error checking {ticker}: {e}")

    if alerts:
        lines = ["Unusual Volume Alert", "=" * 40, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
        for a in alerts:
            lines += [
                f"{a['ticker']:<6} — {a['ratio']}x normal volume",
                f"         Price : ${a['price']} ({a['pct']:+.1f}%)",
                f"         Today : {a['curr_vol']:,} shares",
                f"         Avg   : {a['avg_vol']:,} shares",
                ""
            ]
        lines += ["=" * 40,
                  "Unusual volume can signal big news, earnings leaks, or institutional moves.",
                  "This is an alert only — Evelyn will not trade automatically."]
        send_email_fn("Evelyn: Unusual Volume — " + ", ".join(a["ticker"] for a in alerts),
                      "\n".join(lines))

# ══════════════════════════════════════════════════════════════════
#   4. INSIDER TRADING TRACKER
# ══════════════════════════════════════════════════════════════════

def check_insider_trading(tickers, send_email_fn):
    """Check for recent insider transactions using Yahoo Finance."""
    alerts = []
    for ticker in tickers:
        try:
            data   = fetch_json(f"https://query1.finance.yahoo.com/v11/finance/quoteSummary/{ticker}?modules=insiderTransactions")
            result = data.get("quoteSummary", {}).get("result", [{}])[0]
            transactions = result.get("insiderTransactions", {}).get("transactions", [])
            cutoff = datetime.now() - timedelta(days=30)

            for tx in transactions[:10]:
                ts       = tx.get("startDate", {}).get("raw", 0)
                tx_date  = datetime.fromtimestamp(ts)
                if tx_date < cutoff:
                    continue
                shares   = tx.get("shares", {}).get("raw", 0)
                value    = tx.get("value", {}).get("raw", 0)
                name     = tx.get("filerName", "Unknown")
                relation = tx.get("filerRelation", "")
                tx_text  = tx.get("transactionText", "")
                is_buy   = "purchase" in tx_text.lower() or "buy" in tx_text.lower()
                is_sell  = "sale" in tx_text.lower() or "sell" in tx_text.lower()
                if not (is_buy or is_sell):
                    continue
                alerts.append({
                    "ticker":   ticker,
                    "name":     name,
                    "relation": relation,
                    "action":   "BUY" if is_buy else "SELL",
                    "shares":   shares,
                    "value":    value,
                    "date":     tx_date.strftime("%Y-%m-%d")
                })
                log.info(f"[INSIDER] {ticker}: {name} {('bought' if is_buy else 'sold')} {shares:,} shares")
        except Exception as e:
            log.warning(f"[INSIDER] Error checking {ticker}: {e}")

    if alerts:
        lines = ["Insider Trading Alert", "=" * 40, f"Date: {datetime.now().strftime('%Y-%m-%d')}", ""]
        for a in alerts:
            action_col = "BOUGHT" if a["action"] == "BUY" else "SOLD"
            lines += [
                f"{a['ticker']:<6} — {action_col}",
                f"         Who   : {a['name']} ({a['relation']})",
                f"         Shares: {a['shares']:,}",
                f"         Value : ${a['value']:,}" if a['value'] else "",
                f"         Date  : {a['date']}",
                ""
            ]
        lines += ["=" * 40,
                  "Insiders buying their own stock is often a bullish signal.",
                  "Insiders selling can mean many things — research before acting.",
                  "This is an alert only — Evelyn will not trade automatically."]
        send_email_fn("Evelyn: Insider Activity — " + ", ".join(set(a["ticker"] for a in alerts)),
                      "\n".join(lines))

# ══════════════════════════════════════════════════════════════════
#   SUMMARY
# ══════════════════════════════════════════════════════════════════

def get_monitors_summary():
    """Return current monitor settings for the dashboard."""
    m = load_monitors()
    return {
        "price_targets":    m.get("price_targets", {}),
        "earnings_alerts":  m.get("earnings_alerts", True),
        "volume_alerts":    m.get("volume_alerts", True),
        "volume_threshold": m.get("volume_threshold", 2.0),
        "insider_alerts":   m.get("insider_alerts", True),
    }
