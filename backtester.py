
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

import yfinance as yf

from app_config import load_config


def run_backtest(symbol: str, start: str, end: str | None = None, starting_cash: float = 10000.0, trade_size: float = 500.0, cfg: Dict | None = None):
    cfg = cfg or load_config()
    end = end or datetime.now().strftime('%Y-%m-%d')
    hist = yf.Ticker(symbol).history(start=start, end=end, interval='1d')
    if hist.empty or len(hist) < 30:
        raise RuntimeError('Not enough data for backtest')

    closes = [float(x) for x in hist['Close'].tolist()]
    dates = [str(i.date()) for i in hist.index]
    cash = float(starting_cash)
    shares = 0.0
    trades: List[Dict] = []
    max_trade = float(cfg.get('max_trade_amount', trade_size) or trade_size)
    buy_size = min(trade_size, max_trade)

    for idx in range(20, len(closes)):
        window = closes[:idx+1]
        price = window[-1]
        ma20 = sum(window[-20:]) / 20
        ma50 = sum(window[-50:]) / 50 if len(window) >= 50 else ma20
        # cheap RSI approximation
        period = 14
        if len(window) >= period + 1:
            gains, losses = [], []
            for i in range(len(window)-period, len(window)):
                delta = window[i] - window[i-1]
                gains.append(max(delta, 0))
                losses.append(abs(min(delta, 0)))
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period if sum(losses) else 0.0001
            rsi = 100 - (100 / (1 + (avg_gain / avg_loss)))
        else:
            rsi = 50

        if rsi < float(cfg.get('strategy_rsi_buy_below', 35)) and price > ma20 and cash >= buy_size:
            qty = round(buy_size / price, 6)
            cash -= buy_size
            shares += qty
            trades.append({'date': dates[idx], 'side': 'BUY', 'price': round(price,2), 'qty': qty, 'cash': round(cash,2)})
        elif shares > 0 and (rsi > 65 or price < ma50):
            cash += shares * price
            trades.append({'date': dates[idx], 'side': 'SELL', 'price': round(price,2), 'qty': round(shares,6), 'cash': round(cash,2)})
            shares = 0.0

    final_value = cash + shares * closes[-1]
    return {
        'ok': True,
        'symbol': symbol,
        'start': start,
        'end': end,
        'starting_cash': round(starting_cash, 2),
        'ending_value': round(final_value, 2),
        'return_pct': round(((final_value - starting_cash) / starting_cash) * 100, 2),
        'open_shares': round(shares, 6),
        'trades': trades[-20:],
        'trade_count': len(trades),
    }
