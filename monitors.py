from urllib.error import HTTPError

def check_insider_trading(tickers, send_email_fn):
    """Check for recent insider transactions using Yahoo Finance."""

    m = load_monitors()

    # Respect config setting
    if not m.get("insider_alerts", True):
        return

    alerts = []

    for ticker in tickers:
        ticker = ticker.upper()

        try:
            data = fetch_json(
                f"https://query1.finance.yahoo.com/v11/finance/quoteSummary/{ticker}?modules=insiderTransactions"
            )

            result = data.get("quoteSummary", {}).get("result", [{}])[0]
            transactions = result.get("insiderTransactions", {}).get("transactions", [])
            cutoff = datetime.now() - timedelta(days=30)

            for tx in transactions[:10]:
                ts = tx.get("startDate", {}).get("raw", 0)
                tx_date = datetime.fromtimestamp(ts)

                if tx_date < cutoff:
                    continue

                shares = tx.get("shares", {}).get("raw", 0)
                value = tx.get("value", {}).get("raw", 0)
                name = tx.get("filerName", "Unknown")
                relation = tx.get("filerRelation", "")
                tx_text = tx.get("transactionText", "")

                is_buy = "purchase" in tx_text.lower() or "buy" in tx_text.lower()
                is_sell = "sale" in tx_text.lower() or "sell" in tx_text.lower()

                if not (is_buy or is_sell):
                    continue

                alerts.append({
                    "ticker": ticker,
                    "name": name,
                    "relation": relation,
                    "action": "BUY" if is_buy else "SELL",
                    "shares": shares,
                    "value": value,
                    "date": tx_date.strftime("%Y-%m-%d")
                })

                log.info(f"[INSIDER] {ticker}: {name} {('bought' if is_buy else 'sold')} {shares:,} shares")

        except HTTPError as e:
            # Silent skip for Yahoo 404 issues
            if e.code == 404:
                continue
            log.warning(f"[INSIDER] Error checking {ticker}: {e}")

        except Exception as e:
            log.warning(f"[INSIDER] Error checking {ticker}: {e}")

    if alerts:
        lines = [
            "Insider Trading Alert",
            "=" * 40,
            f"Date: {datetime.now().strftime('%Y-%m-%d')}",
            ""
        ]

        for a in alerts:
            action_col = "BOUGHT" if a["action"] == "BUY" else "SOLD"
            lines += [
                f"{a['ticker']:<6} — {action_col}",
                f"         Who   : {a['name']} ({a['relation']})",
                f"         Shares: {a['shares']:,}",
                f"         Value : ${a['value']:,}" if a["value"] else "",
                f"         Date  : {a['date']}",
                ""
            ]

        lines += [
            "=" * 40,
            "Insiders buying their own stock is often a bullish signal.",
            "Insiders selling can mean many things — research before acting.",
            "This is an alert only — Evelyn will not trade automatically."
        ]

        send_email_fn(
            "Evelyn: Insider Activity — " + ", ".join(set(a["ticker"] for a in alerts)),
            "\n".join(lines)
        )
