"""
========================================
  Evelyn — Smart Stock Trading Assistant
  Features: Email Alerts + Weekly Portfolio Summary
========================================

WHAT THIS BOT DOES:
  - Automatically buys a fixed dollar amount of your chosen stocks
  - Runs on a schedule you set (daily, weekly, monthly)
  - Sends you an email every time a trade is made
  - Emails you a weekly portfolio summary every Sunday evening
  - Logs every trade so you can track activity
  - Has safety limits to protect you from big mistakes

SETUP INSTRUCTIONS:
  1. Install Python: https://www.python.org/downloads/
  2. Open Terminal (Mac) or Command Prompt (Windows)
  3. Run: pip install robin_stocks schedule
  4. Fill in your settings in the CONFIG section below
  5. For Gmail, enable "App Passwords":
       Go to myaccount.google.com > Security > 2-Step Verification > App Passwords
       Generate a password for "Mail" and paste it into EMAIL_PASSWORD below
  6. Run: python robinbot.py

IMPORTANT WARNING:
  - This bot uses real money. Start with small amounts.
  - Robinhood may flag automated logins. Use app-based 2FA.
  - Never share your username/password with anyone.
  - Past performance does not guarantee future results.
"""

import robin_stocks.robinhood as rh
import schedule
import time
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import wallet as W
import smart_trader as ST
import ai_picker as AI
import advisor as ADV
import monitors as MON
import os as _os
import json
from pathlib import Path
from app_config import DATA_DIR, LOG_FILE, load_config, ensure_dirs
import alerts as ALERTS
import strategy_engine as SE

ensure_dirs()

# ============================================================
#   CONFIG - EDIT THIS SECTION TO CUSTOMIZE YOUR BOT
# ============================================================

# --- Robinhood Credentials ---
RH_USERNAME = _os.environ.get("EVELYN_RH_USERNAME", "")
RH_PASSWORD = _os.environ.get("EVELYN_RH_PASSWORD", "")

# --- Stocks to DCA into ---
# Format: { "TICKER": dollar_amount_per_cycle }
DCA_STOCKS = {
    "AAPL": 10,   # Buy $10 of Apple each cycle
    "MSFT": 10,   # Buy $10 of Microsoft each cycle
    "SPY":  20,   # Buy $20 of S&P 500 ETF each cycle
}

# --- Schedule ---
# Options: "daily", "weekly", "monthly"
BUY_FREQUENCY = "weekly"

# --- Safety Limit ---
MAX_SPEND_PER_CYCLE = 100  # Max $ the bot can spend in one cycle

# ============================================================
#   WALLET / BUDGET CONFIG
# ============================================================
# The bot will ONLY spend from its dedicated wallet balance.
# It will NEVER touch any other money in your Robinhood account.
#
# To add funds to the bot's wallet, use the web UI (Wallet tab)
# or call: python -c "import wallet; wallet.deposit(50, 'Top up')"
#
# The bot checks the wallet before every trade. If there isn't
# enough in the wallet, the trade is skipped — not your bank.

USE_WALLET = True   # Set False to disable wallet protection (not recommended)

# ============================================================
#   SMART TRADING CONFIG
# ============================================================

# --- Profit Target (auto-sell) ---
# Sell a stock automatically when it gains this much from your avg buy price
PROFIT_TARGET_PCT  = 20.0   # e.g. 20.0 = sell when up 20%
PROFIT_TARGET_ON   = True   # Set False to disable

# --- Stop-Loss (auto-sell) ---
# Sell a stock automatically when it drops this much from your avg buy price
STOP_LOSS_PCT      = 10.0   # e.g. 10.0 = sell when down 10%
STOP_LOSS_ON       = True   # Set False to disable

# --- News Research (smart buy filter) ---
# Checks Yahoo Finance news before each buy cycle.
# Skips buying a stock if recent news sentiment is too negative.
NEWS_CHECK_ON      = True   # Set False to always buy regardless of news
NEWS_MIN_SCORE     = -2     # Allow buys down to this sentiment score (-5 worst / +5 best)

# How often to check for profit target / stop-loss (in minutes)
MONITOR_INTERVAL   = 60

# ============================================================
#   AI STOCK PICKER CONFIG
# ============================================================
AI_MODE            = False  # True = AI picks stocks, False = you pick manually
AI_NUM_STOCKS      = 5      # How many stocks the AI picks at once
AI_DOLLAR_EACH     = 20     # How much $ to invest in each AI pick
AI_REPICK_DAYS     = 7      # How often the AI refreshes its picks (days)

# ============================================================
#   ALERT ONLY MODE
# ============================================================
# True  = bot emails you buy/sell suggestions, YOU trade in Robinhood
# False = bot trades automatically (use with caution)
# Toggle this anytime from the dashboard Schedule tab.

ALERT_ONLY = True   # True = alerts only | False = auto trade

# --- Dry Run Mode ---
# Set to True to TEST without spending real money
DRY_RUN = True   # <-- Change to False when ready to go live

# ============================================================
#   EMAIL CONFIG - Fill this in to receive alerts
# ============================================================

EMAIL_ENABLED = True                        # Set to False to disable emails

EMAIL_SENDER = _os.environ.get("EVELYN_EMAIL_SENDER", "")
EMAIL_PASSWORD = _os.environ.get("EVELYN_EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = _os.environ.get("EVELYN_EMAIL_RECIPIENT", "")

SMTP_SERVER = "smtp.gmail.com"              # Change if not using Gmail
SMTP_PORT = 587


# ============================================================
#   LOAD SHARED CONFIG
# ============================================================

_CFG = load_config()
RH_USERNAME = _CFG.get('rh_username', RH_USERNAME)
RH_PASSWORD = _CFG.get('rh_password', RH_PASSWORD)
DCA_STOCKS = _CFG.get('dca_stocks', DCA_STOCKS)
BUY_FREQUENCY = _CFG.get('buy_frequency', BUY_FREQUENCY)
MAX_SPEND_PER_CYCLE = _CFG.get('max_spend', MAX_SPEND_PER_CYCLE)
USE_WALLET = _CFG.get('use_wallet', USE_WALLET)
PROFIT_TARGET_PCT = _CFG.get('profit_target_pct', PROFIT_TARGET_PCT)
PROFIT_TARGET_ON = _CFG.get('profit_target_on', PROFIT_TARGET_ON)
STOP_LOSS_PCT = _CFG.get('stop_loss_pct', STOP_LOSS_PCT)
STOP_LOSS_ON = _CFG.get('stop_loss_on', STOP_LOSS_ON)
NEWS_CHECK_ON = _CFG.get('news_check_on', NEWS_CHECK_ON)
NEWS_MIN_SCORE = _CFG.get('news_min_score', NEWS_MIN_SCORE)
MONITOR_INTERVAL = _CFG.get('monitor_interval', MONITOR_INTERVAL)
AI_MODE = _CFG.get('ai_mode', AI_MODE)
AI_NUM_STOCKS = _CFG.get('ai_num_stocks', AI_NUM_STOCKS)
AI_DOLLAR_EACH = _CFG.get('ai_dollar_each', AI_DOLLAR_EACH)
ALERT_ONLY = _CFG.get('alert_only', ALERT_ONLY)
DRY_RUN = _CFG.get('dry_run', DRY_RUN)
BROKER = (_CFG.get('broker', 'robinhood') or 'robinhood').lower()
ALPACA_KEY = _CFG.get('alpaca_key', '')
ALPACA_SECRET = _CFG.get('alpaca_secret', '')
ALPACA_PAPER = _CFG.get('alpaca_paper', True)
EMAIL_ENABLED = _CFG.get('email_enabled', EMAIL_ENABLED)
EMAIL_SENDER = _CFG.get('email_sender', EMAIL_SENDER)
EMAIL_PASSWORD = _CFG.get('email_password', EMAIL_PASSWORD)
EMAIL_RECIPIENT = _CFG.get('email_recipient', EMAIL_RECIPIENT)
SMTP_SERVER = _CFG.get('smtp_server', SMTP_SERVER)
SMTP_PORT = _CFG.get('smtp_port', SMTP_PORT)
TELEGRAM_ENABLED = _CFG.get('telegram_enabled', False)
STRATEGY_ENABLED = _CFG.get('strategy_enabled', True)
STRATEGY_MODE = _CFG.get('strategy_mode', 'hybrid')
DIP_BUY_ENABLED = _CFG.get('dip_buy_enabled', True)
DIP_BUY_PCT = _CFG.get('dip_buy_pct', 5.0)
DIP_BUY_MULTIPLIER = _CFG.get('dip_buy_multiplier', 2.0)
MAX_TRADE_AMOUNT = _CFG.get('max_trade_amount', 50)
MAX_TRADES_PER_DAY = _CFG.get('max_trades_per_day', 5)
MAX_DAILY_SPEND = _CFG.get('max_daily_spend', 250)
LIVE_TRADING_UNLOCKED = _CFG.get('live_trading_unlocked', False)

# ============================================================
#   LOGGING SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
        logging.StreamHandler()
    ]
)
log = logging.getLogger()

# ============================================================
#   EMAIL FUNCTIONS
# ============================================================

def send_email(subject, body):
    """Send an email notification."""
    if not EMAIL_ENABLED:
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECIPIENT

        # Plain text version
        text_part = MIMEText(body, "plain")
        msg.attach(text_part)

        # HTML version (nicer formatting)
        html_body = body.replace("\n", "<br>").replace(" ", "&nbsp;")
        html_part = MIMEText(
            f"<html><body style='font-family:Arial;font-size:14px;'>{html_body}</body></html>",
            "html"
        )
        msg.attach(html_part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())

        log.info(f"Email sent: {subject}")
    except Exception as e:
        log.error(f"Failed to send email: {e}")


def send_trade_alert(ticker, dollar_amount, shares, price, success):
    """Send an email alert after a trade attempt."""
    status = "SUCCESS" if success else "FAILED"
    mode = " [DRY RUN]" if DRY_RUN else ""
    subject = f"Evelyn{mode}: {status} - {ticker} Trade"
    body = f"""
Evelyn Trade Alert{mode}
{'=' * 40}
Status    : {status}
Stock     : {ticker}
Amount    : ${dollar_amount:.2f}
Shares    : {shares:.6f}
Price     : ${price:.2f}
Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'=' * 40}
This is an automated message from your Evelyn.
"""
    ALERTS.send_alert(subject, body, email_func=send_email, cfg=load_config())


def send_weekly_summary():
    """Fetch portfolio data and send a weekly summary email."""
    log.info("Generating weekly portfolio summary...")

    if not login():
        log.error("Could not log in for weekly summary.")
        return

    try:
        # Get portfolio value
        portfolio = rh.profiles.load_portfolio_profile()
        equity = float(portfolio.get("equity", 0))
        prev_equity = float(portfolio.get("adjusted_equity_previous_close", equity))
        day_change = equity - prev_equity
        day_change_pct = (day_change / prev_equity * 100) if prev_equity else 0

        # Get holdings
        holdings = rh.account.build_holdings()

        lines = []
        lines.append("Weekly Portfolio Summary")
        lines.append("=" * 40)
        lines.append(f"Date       : {datetime.now().strftime('%Y-%m-%d')}")
        lines.append(f"Total Value: ${equity:,.2f}")
        lines.append(f"Day Change : ${day_change:+.2f} ({day_change_pct:+.2f}%)")
        lines.append("")
        lines.append("Your Holdings:")
        lines.append("-" * 40)

        if holdings:
            for ticker, data in holdings.items():
                qty        = float(data.get("quantity", 0))
                avg_buy    = float(data.get("average_buy_price", 0))
                curr_price = float(data.get("price", 0))
                total_val  = float(data.get("equity", 0))
                gain       = float(data.get("percent_change", 0))
                lines.append(
                    f"{ticker:<6} | Qty: {qty:.4f} | Avg: ${avg_buy:.2f} | "
                    f"Now: ${curr_price:.2f} | Value: ${total_val:.2f} | "
                    f"Gain: {gain:+.2f}%"
                )
        else:
            lines.append("No holdings found.")

        lines.append("")
        lines.append("=" * 40)
        lines.append("This is an automated message from your Evelyn.")

        body = "\n".join(lines)
        send_email("Evelyn: Weekly Portfolio Summary", body)
        log.info("Weekly summary email sent.")

    except Exception as e:
        log.error(f"Error generating weekly summary: {e}")
        send_email("Evelyn: Weekly Summary Failed", f"Could not generate summary.\nError: {e}")

    if BROKER != 'alpaca':
        rh.logout()




TRADE_GUARD_FILE = Path(DATA_DIR) / 'trade_guard.json'


def _load_guard():
    today = datetime.now().strftime('%Y-%m-%d')
    if TRADE_GUARD_FILE.exists():
        try:
            data = json.loads(TRADE_GUARD_FILE.read_text())
        except Exception:
            data = {}
    else:
        data = {}
    if data.get('date') != today:
        data = {'date': today, 'trade_count': 0, 'spent': 0.0}
    return data


def _save_guard(data):
    TRADE_GUARD_FILE.write_text(json.dumps(data, indent=2))


def _risk_check(amount):
    guard = _load_guard()
    if float(amount) > float(MAX_TRADE_AMOUNT):
        return False, f'Trade amount ${amount:.2f} is above max trade amount ${float(MAX_TRADE_AMOUNT):.2f}'
    if guard.get('trade_count', 0) >= int(MAX_TRADES_PER_DAY):
        return False, f'Max trades per day reached: {MAX_TRADES_PER_DAY}'
    if guard.get('spent', 0.0) + float(amount) > float(MAX_DAILY_SPEND):
        return False, f'Daily spend limit would be exceeded: ${MAX_DAILY_SPEND:.2f}'
    return True, ''


def _record_trade(amount):
    guard = _load_guard()
    guard['trade_count'] = int(guard.get('trade_count', 0)) + 1
    guard['spent'] = round(float(guard.get('spent', 0.0)) + float(amount), 2)
    _save_guard(guard)


def _strategy_decision(ticker, amount):
    if not STRATEGY_ENABLED:
        return True, amount, 'Strategy disabled'
    try:
        result = SE.evaluate_symbol(ticker, load_config())
    except Exception as e:
        return True, amount, f'Strategy unavailable: {e}'
    if result['action'] == 'SKIP':
        return False, amount, result['reason']
    use_amount = float(amount)
    if DIP_BUY_ENABLED and (result.get('dip_from_high_pct') or 0) >= float(DIP_BUY_PCT):
        use_amount = min(float(MAX_TRADE_AMOUNT), round(float(amount) * float(DIP_BUY_MULTIPLIER), 2))
        return True, use_amount, result['reason'] + f' | Dip boost applied to ${use_amount:.2f}'
    return True, use_amount, result['reason']
# ============================================================
#   TRADING FUNCTIONS
# ============================================================

def login():
    """Prepare the active broker session."""
    if BROKER == 'alpaca':
        log.info("Checking Alpaca connection...")
        try:
            import alpaca_adapter as alp
            alp.test_connection(_CFG)
            log.info("Alpaca connection ready.")
            return True
        except Exception as e:
            log.error(f"Alpaca connection failed: {e}")
            return False

    log.info("Logging into Robinhood...")
    try:
        rh.login(RH_USERNAME, RH_PASSWORD)
        log.info("Login successful.")
        return True
    except Exception as e:
        log.error(f"Login failed: {e}")
        return False


def get_current_price(ticker):
    """Get the latest price for a stock."""
    if BROKER == 'alpaca':
        try:
            import alpaca_adapter as alp
            return float(alp.get_current_price(ticker))
        except Exception as e:
            log.error(f"Could not get Alpaca price for {ticker}: {e}")
            return None
    try:
        quote = rh.stocks.get_latest_price(ticker)
        return float(quote[0])
    except Exception as e:
        log.error(f"Could not get price for {ticker}: {e}")
        return None


def place_buy_order(ticker, dollar_amount):
    if BROKER == 'alpaca':
        import alpaca_adapter as alp
        return alp.buy_notional(ticker, dollar_amount, _CFG)
    return rh.orders.order_buy_fractional_by_price(
        ticker, dollar_amount, timeInForce="gfd", extendedHours=False)


def get_buy_scores(ticker):
    """Get news + trend scores for a ticker to include in alert emails."""
    try:
        import urllib.request
        import xml.etree.ElementTree as ET
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            root = ET.fromstring(resp.read())
        headlines  = [i.findtext("title","") for i in root.findall(".//item")[:5]]
        news_score, _ = ST.score_sentiment([{"title": h} for h in headlines])
        price_data    = AI.fetch_price_data(ticker)
        trend_score, trend_reason = AI.score_price_trend(price_data)
        return news_score, trend_score, trend_reason, headlines
    except Exception:
        return 0, 0, "", []


def buy_fractional_share(ticker, dollar_amount):
    """Send a buy alert or place a real order depending on ALERT_ONLY mode."""

    allowed, adjusted_amount, strategy_reason = _strategy_decision(ticker, dollar_amount)
    if not allowed:
        msg = f"[STRATEGY] Skipping {ticker}: {strategy_reason}"
        log.warning(msg)
        ALERTS.send_alert('Evelyn: Strategy skipped trade', msg, email_func=send_email, cfg=load_config())
        return

    risk_ok, risk_reason = _risk_check(adjusted_amount)
    if not risk_ok:
        log.warning(f"[RISK] {risk_reason}")
        ALERTS.send_alert('Evelyn: Risk control blocked trade', risk_reason, email_func=send_email, cfg=load_config())
        return

    dollar_amount = adjusted_amount
    price  = get_current_price(ticker)
    if price is None:
        log.error(f"Could not get price for {ticker}")
        return
    shares = round(dollar_amount / price, 6)
    log.info(f"[STRATEGY] {ticker}: {strategy_reason}")

    # ── Alert only — no trading ───────────────────────────────
    if ALERT_ONLY:
        news_score, trend_score, trend_reason, headlines = get_buy_scores(ticker)
        subject, body = ADV.build_buy_alert(
            ticker, price,
            news_score, trend_score,
            trend_reason, headlines
        )
        log.info(f"[ALERT] BUY suggestion sent for {ticker} @ ${price:.2f}")
        ALERTS.send_alert(subject, body, email_func=send_email, cfg=load_config())
        return

    # ── News sentiment check ──────────────────────────────────
    if NEWS_CHECK_ON and not DRY_RUN:
        ST.NEWS_CHECK_ENABLED = True
        ST.NEWS_MIN_SCORE     = NEWS_MIN_SCORE
        allowed, reason = ST.should_buy(ticker)
        if not allowed:
            log.warning(f"[NEWS] Skipping {ticker}: {reason}")
            send_email(f"Evelyn: Skipped {ticker} — negative news",
                       f"Skipped {ticker} due to: {reason}")
            return

    # ── Wallet check ──────────────────────────────────────────
    if USE_WALLET and not DRY_RUN:
        balance = W.get_balance()
        if balance < dollar_amount:
            msg = (f"[WALLET] Skipping {ticker}: need ${dollar_amount:.2f} "
                   f"but wallet only has ${balance:.2f}.")
            log.warning(msg)
            send_email("Evelyn: Wallet too low — trade skipped", msg)
            return
        W.deduct(dollar_amount, ticker)

    log.info(f"{'[DRY RUN] ' if DRY_RUN else ''}Buying ${dollar_amount} of {ticker} "
             f"({shares} shares @ ${price:.2f})")

    if DRY_RUN:
        log.info("[DRY RUN] Order NOT placed.")
        _record_trade(dollar_amount)
        send_trade_alert(ticker, dollar_amount, shares, price, success=True)
        return

    if not LIVE_TRADING_UNLOCKED:
        msg = 'Live trading is locked by security settings. Unlock it in the dashboard before placing real orders.'
        log.warning(msg)
        ALERTS.send_alert('Evelyn: Live trade blocked', msg, email_func=send_email, cfg=load_config())
        return

    try:
        place_buy_order(ticker, dollar_amount)
        _record_trade(dollar_amount)
        log.info(f"Order placed with {BROKER}: {ticker}")
        send_trade_alert(ticker, dollar_amount, shares, price, success=True)
    except Exception as e:
        log.error(f"Order failed for {ticker}: {e}")
        if USE_WALLET:
            W.refund(dollar_amount, ticker, str(e))
        send_trade_alert(ticker, dollar_amount, shares, price, success=False)


def run_dca_cycle():
    """Run one full DCA buy cycle — manual or AI mode."""
    log.info("=" * 50)
    log.info(f"Starting DCA cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Determine which stocks to trade ──────────────────────
    if AI_MODE:
        log.info("[AI] AI mode active — running stock picker...")
        picks = AI.pick_stocks(num_stocks=AI_NUM_STOCKS)
        AI.save_picks(picks)
        if ALERT_ONLY:
            subject, body = ADV.build_ai_suggestions_email(picks, AI_DOLLAR_EACH)
            ALERTS.send_alert(subject, body, email_func=send_email, cfg=load_config())
            log.info(f"[ALERT] AI suggestions sent for: {[p['ticker'] for p in picks]}")
            return
        trade_stocks = {p["ticker"]: AI_DOLLAR_EACH for p in picks}
        ALERTS.send_alert("Evelyn: AI picked new stocks", AI.format_picks_email(picks, AI_DOLLAR_EACH), email_func=send_email, cfg=load_config())
        log.info(f"[AI] Picks: {list(trade_stocks.keys())}")
    else:
        trade_stocks = DCA_STOCKS
        log.info(f"[{'ALERT' if ALERT_ONLY else 'MANUAL'}] Stock list: {list(trade_stocks.keys())}")

    # Safety check
    total_spend = sum(trade_stocks.values())
    if total_spend > MAX_SPEND_PER_CYCLE:
        msg = (f"Total spend ${total_spend} exceeds MAX_SPEND_PER_CYCLE "
               f"${MAX_SPEND_PER_CYCLE}. Aborting.")
        log.error(msg)
        ALERTS.send_alert("Evelyn: Cycle Aborted", msg, email_func=send_email, cfg=load_config())
        return

    # Wallet check
    if USE_WALLET and not DRY_RUN:
        balance = W.get_balance()
        log.info(f"[WALLET] Current balance: ${balance:.2f} | Cycle needs: ${total_spend:.2f}")
        if balance <= 0:
            msg = (f"[WALLET] Bot wallet is empty (${balance:.2f}). "
                   f"Add funds via the web UI Wallet tab.")
            log.warning(msg)
            send_email("Evelyn: Wallet Empty — cycle skipped", msg)
            return
        if balance < total_spend:
            log.warning(
                f"[WALLET] Wallet (${balance:.2f}) is less than full cycle cost "
                f"(${total_spend:.2f}). Will buy what it can afford."
            )

    # Skip weekends
    if datetime.now().weekday() >= 5:
        log.info("Market is closed (weekend). Skipping cycle.")
        return

    if not login():
        ALERTS.send_alert("Evelyn: Broker Login Failed", f"The bot could not connect to the active broker: {BROKER}.", email_func=send_email, cfg=load_config())
        return

    for ticker, amount in trade_stocks.items():
        buy_fractional_share(ticker, amount)
        time.sleep(2)

    log.info(f"DCA cycle complete. Total invested: ${total_spend}")
    log.info("=" * 50)
    if BROKER != 'alpaca':
        rh.logout()


def run_exit_monitor():
    """
    Check all holdings for profit target or stop-loss triggers.
    In ALERT_ONLY mode sends email suggestions instead of selling.
    """
    if not (PROFIT_TARGET_ON or STOP_LOSS_ON):
        return

    # Only run during market hours (Mon-Fri, 9:30am-4pm)
    now     = datetime.now()
    weekday = now.weekday()
    hour    = now.hour + now.minute / 60
    if weekday >= 5 or not (9.5 <= hour <= 16.0):
        return

    log.info("[MONITOR] Running exit condition check...")
    if not login():
        return

    try:
        holdings = rh.account.build_holdings()

        for ticker, data in holdings.items():
            qty       = float(data.get("quantity", 0))
            avg_buy   = float(data.get("average_buy_price", 0))
            cur_price = float(data.get("price", 0))
            if qty <= 0 or avg_buy <= 0 or cur_price <= 0:
                continue
            pct_change = ((cur_price - avg_buy) / avg_buy) * 100

            reason = None
            if PROFIT_TARGET_ON and pct_change >= PROFIT_TARGET_PCT:
                reason = f"Profit target hit: {pct_change:+.1f}% (target +{PROFIT_TARGET_PCT}%)"
            elif STOP_LOSS_ON and pct_change <= -STOP_LOSS_PCT:
                reason = f"Stop-loss triggered: {pct_change:+.1f}% (limit -{STOP_LOSS_PCT}%)"

            if reason:
                if ALERT_ONLY:
                    # Send alert instead of selling
                    subject, body = ADV.build_sell_alert(
                        ticker, qty, avg_buy, cur_price, pct_change, reason)
                    ALERTS.send_alert(subject, body, email_func=send_email, cfg=load_config())
                    log.info(f"[ALERT] SELL suggestion sent for {ticker}: {reason}")
                else:
                    # Actually sell
                    ST.PROFIT_TARGET_PCT = PROFIT_TARGET_PCT if PROFIT_TARGET_ON else 999
                    ST.STOP_LOSS_PCT     = STOP_LOSS_PCT     if STOP_LOSS_ON     else 999
                    actions = ST.check_exit_conditions(holdings, rh)
                    if actions:
                        send_email("Evelyn: Auto-Sell Executed", ST.format_exit_email(actions))
                    break
            else:
                log.info(f"[MONITOR] {ticker}: {pct_change:+.1f}% — holding")

    except Exception as e:
        log.error(f"[MONITOR] Error during exit check: {e}")
    finally:
        rh.logout()


# ============================================================
#   SCHEDULE SETUP
# ============================================================

def setup_schedule():
    """Set up buying schedule and weekly summary."""

    # DCA buying schedule
    if BUY_FREQUENCY == "daily":
        schedule.every().day.at("10:00").do(run_dca_cycle)
        log.info("Scheduled: Daily buys at 10:00 AM")

    elif BUY_FREQUENCY == "weekly":
        schedule.every().monday.at("10:00").do(run_dca_cycle)
        log.info("Scheduled: Weekly buys every Monday at 10:00 AM")

    elif BUY_FREQUENCY == "monthly":
        def monthly_check():
            if datetime.now().day == 1:
                run_dca_cycle()
        schedule.every().day.at("10:00").do(monthly_check)
        log.info("Scheduled: Monthly buys on the 1st at 10:00 AM")

    else:
        log.error(f"Unknown BUY_FREQUENCY: '{BUY_FREQUENCY}'. Use 'daily', 'weekly', or 'monthly'.")

    # Weekly portfolio summary every Sunday at 6:00 PM
    schedule.every().sunday.at("18:00").do(send_weekly_summary)
    log.info("Scheduled: Weekly portfolio summary every Sunday at 6:00 PM")

    # Exit condition monitor (profit target + stop-loss)
    if PROFIT_TARGET_ON or STOP_LOSS_ON:
        schedule.every(MONITOR_INTERVAL).minutes.do(run_exit_monitor)
        log.info(f"Scheduled: Exit monitor every {MONITOR_INTERVAL} minutes")

    # Price target, volume, insider, earnings monitors
    schedule.every(30).minutes.do(run_monitors)
    schedule.every().day.at("08:00").do(run_earnings_check)
    log.info("Scheduled: Price targets + volume + insider checks every 30 min")
    log.info("Scheduled: Earnings calendar check daily at 8:00 AM")

def run_monitors():
    """Run price target, unusual volume and insider trading checks."""
    cfg = {}
    try:
        from pathlib import Path
        import json as _json
        if Path("bot_config.json").exists():
            with open("bot_config.json") as f:
                cfg = _json.load(f)
    except Exception:
        pass

    tickers  = list((cfg.get("dca_stocks") or DCA_STOCKS).keys())
    mon_cfg  = MON.load_monitors()

    # Price targets
    MON.check_price_targets(send_email)

    # Unusual volume
    if mon_cfg.get("volume_alerts", True):
        threshold = mon_cfg.get("volume_threshold", 2.0)
        MON.check_unusual_volume(tickers, threshold, send_email)

    # Insider trading (once per day is enough — skip if already ran today)
    if mon_cfg.get("insider_alerts", True):
        last = mon_cfg.get("insider_last_run", "")
        today = datetime.now().strftime("%Y-%m-%d")
        if last != today:
            MON.check_insider_trading(tickers, send_email)
            mon_cfg["insider_last_run"] = today
            MON.save_monitors(mon_cfg)

def run_earnings_check():
    """Check earnings calendar for upcoming reports."""
    cfg = {}
    try:
        from pathlib import Path
        import json as _json
        if Path("bot_config.json").exists():
            with open("bot_config.json") as f:
                cfg = _json.load(f)
    except Exception:
        pass
    tickers = list((cfg.get("dca_stocks") or DCA_STOCKS).keys())
    mon_cfg = MON.load_monitors()
    if mon_cfg.get("earnings_alerts", True):
        MON.check_earnings_calendar(tickers, send_email)


# ============================================================
#   MAIN
# ============================================================

if __name__ == "__main__":
    log.info("Evelyn Starting...")
    log.info(f"Mode     : {'DRY RUN (no real trades)' if DRY_RUN else 'LIVE TRADING'}")
    log.info(f"Stocks   : {DCA_STOCKS}")
    log.info(f"Frequency: {BUY_FREQUENCY}")
    log.info(f"Email    : {'Enabled -> ' + EMAIL_RECIPIENT if EMAIL_ENABLED else 'Disabled'}")
    if USE_WALLET:
        bal = W.get_balance()
        log.info(f"Wallet   : ${bal:.2f} available")

    setup_schedule()

    # Send a startup notification
    send_email(
        "Evelyn Started",
        f"Your Robinhood Evelyn has started.\n\n"
        f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n"
        f"Stocks: {', '.join(DCA_STOCKS.keys())}\n"
        f"Frequency: {BUY_FREQUENCY}\n"
        f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    log.info("Bot is running. Press CTRL+C to stop.")
    log.info("Waiting for next scheduled cycle...\n")

    while True:
        schedule.run_pending()
        time.sleep(30)
