
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import yfinance as yf

from app_config import load_config


@dataclass
class StrategyDecision:
    symbol: str
    action: str
    score: int
    reason: str
    price: float
    rsi: float | None = None
    ma_short: float | None = None
    ma_long: float | None = None
    dip_from_high_pct: float | None = None


def _rsi(closes: List[float], period: int = 14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i-1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    recent_gains = gains[-period:]
    recent_losses = losses[-period:]
    avg_gain = sum(recent_gains) / period
    avg_loss = sum(recent_losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fetch_history(symbol: str, period: str = '6mo'):
    hist = yf.Ticker(symbol).history(period=period, interval='1d')
    if hist.empty:
        raise RuntimeError(f'No market data for {symbol}')
    return hist


def evaluate_symbol(symbol: str, cfg: Dict | None = None) -> Dict:
    cfg = cfg or load_config()
    hist = fetch_history(symbol)
    closes = [float(x) for x in hist['Close'].tolist()]
    price = closes[-1]
    short_n = int(cfg.get('strategy_ma_short', 20) or 20)
    long_n = int(cfg.get('strategy_ma_long', 50) or 50)
    rsi_period = int(cfg.get('strategy_rsi_period', 14) or 14)
    buy_below = float(cfg.get('strategy_rsi_buy_below', 35) or 35)
    ma_short = sum(closes[-short_n:]) / min(len(closes), short_n)
    ma_long = sum(closes[-long_n:]) / min(len(closes), long_n)
    rsi = _rsi(closes, rsi_period)
    high_60 = max(closes[-60:]) if len(closes) >= 60 else max(closes)
    dip_pct = ((high_60 - price) / high_60 * 100) if high_60 else 0

    score = 0
    reasons = []
    if rsi is not None and rsi <= buy_below:
        score += 2
        reasons.append(f'RSI {rsi:.1f} is below buy level {buy_below}')
    elif rsi is not None and rsi >= 70:
        score -= 2
        reasons.append(f'RSI {rsi:.1f} looks overbought')
    if price >= ma_short >= ma_long:
        score += 2
        reasons.append('Price is above both moving averages')
    elif price < ma_short < ma_long:
        score -= 2
        reasons.append('Price is below both moving averages')
    if cfg.get('dip_buy_enabled', True) and dip_pct >= float(cfg.get('dip_buy_pct', 5.0) or 5.0):
        score += 1
        reasons.append(f'Price is {dip_pct:.1f}% off the recent high')

    if score >= 2:
        action = 'BUY'
    elif score <= -2:
        action = 'SKIP'
    else:
        action = 'HOLD'

    return {
        'symbol': symbol,
        'action': action,
        'score': score,
        'reason': '; '.join(reasons) if reasons else 'No strong signal',
        'price': round(price, 2),
        'rsi': round(rsi, 2) if rsi is not None else None,
        'ma_short': round(ma_short, 2),
        'ma_long': round(ma_long, 2),
        'dip_from_high_pct': round(dip_pct, 2),
    }
