from __future__ import annotations

from typing import Any, Dict, Optional

import yfinance as yf

from app_config import load_config

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
except Exception:
    TradingClient = None
    MarketOrderRequest = None
    OrderSide = None
    TimeInForce = None


def _cfg() -> Dict[str, Any]:
    return load_config()


def _creds(cfg: Optional[Dict[str, Any]] = None):
    cfg = cfg or _cfg()
    key = (cfg.get('alpaca_key') or '').strip()
    secret = (cfg.get('alpaca_secret') or '').strip()
    paper = bool(cfg.get('alpaca_paper', True))
    return key, secret, paper


def sdk_ready() -> bool:
    return TradingClient is not None


def get_client(cfg: Optional[Dict[str, Any]] = None) -> TradingClient:
    if TradingClient is None:
        raise RuntimeError('Alpaca SDK is not installed yet. Rebuild the container after updating requirements.')
    key, secret, paper = _creds(cfg)
    if not key or not secret:
        raise RuntimeError('Save your Alpaca key and secret first.')
    return TradingClient(key, secret, paper=paper)


def test_connection(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    client = get_client(cfg)
    account = client.get_account()
    positions = client.get_all_positions()
    equity = float(getattr(account, 'equity', 0) or 0)
    cash = float(getattr(account, 'cash', 0) or 0)
    last_equity = float(getattr(account, 'last_equity', equity) or equity)
    return {
        'ok': True,
        'equity': round(equity, 2),
        'cash': round(cash, 2),
        'day_chg': round(equity - last_equity, 2),
        'day_pct': round(((equity - last_equity) / last_equity) * 100, 2) if last_equity else 0,
        'num_pos': len(positions),
        'paper': bool(getattr(account, 'account_blocked', False)) is False and bool((cfg or _cfg()).get('alpaca_paper', True)),
        'msg': 'Connected successfully!',
    }


def get_current_price(symbol: str) -> float:
    ticker = yf.Ticker(symbol)
    info = ticker.fast_info
    price = float(info.last_price)
    if price <= 0:
        raise RuntimeError(f'Could not get a live price for {symbol}')
    return price


def get_balance(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return test_connection(cfg)


def buy_notional(symbol: str, notional_amount: float, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    client = get_client(cfg)
    req = MarketOrderRequest(
        symbol=symbol,
        notional=round(float(notional_amount), 2),
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    )
    order = client.submit_order(order_data=req)
    return {
        'id': str(getattr(order, 'id', '')),
        'symbol': symbol,
        'notional': round(float(notional_amount), 2),
        'status': str(getattr(order, 'status', 'accepted')),
    }


def get_positions(cfg: Optional[Dict[str, Any]] = None):
    client = get_client(cfg)
    out = []
    for pos in client.get_all_positions():
        out.append({
            'symbol': getattr(pos, 'symbol', ''),
            'qty': float(getattr(pos, 'qty', 0) or 0),
            'market_value': float(getattr(pos, 'market_value', 0) or 0),
            'unrealized_pl': float(getattr(pos, 'unrealized_pl', 0) or 0),
            'unrealized_plpc': float(getattr(pos, 'unrealized_plpc', 0) or 0) * 100,
        })
    return out
