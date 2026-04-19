"""
Bot Wallet — tracks a dedicated trading budget.
The bot will ONLY spend from this wallet, never touching
any other funds in your Robinhood cash balance.

Wallet state is saved to wallet.json so it persists across restarts.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from app_config import DATA_DIR, ensure_dirs

ensure_dirs()
WALLET_FILE = str(DATA_DIR / 'wallet.json')
log = logging.getLogger()

DEFAULT_WALLET = {
    'balance': 0.0,
    'total_deposited': 0.0,
    'total_spent': 0.0,
    'transactions': []
}

def load_wallet():
    path = Path(WALLET_FILE)
    if path.exists():
        with path.open() as f:
            return json.load(f)
    return DEFAULT_WALLET.copy()

def save_wallet(w):
    ensure_dirs()
    with Path(WALLET_FILE).open('w') as f:
        json.dump(w, f, indent=2)

def get_balance():
    return load_wallet()['balance']

def deposit(amount: float, note: str = 'Manual deposit'):
    if amount <= 0:
        raise ValueError('Deposit amount must be positive.')
    w = load_wallet()
    w['balance'] += amount
    w['total_deposited'] += amount
    w['transactions'].append({
        'type': 'deposit',
        'amount': amount,
        'balance': w['balance'],
        'note': note,
        'timestamp': datetime.now().isoformat()
    })
    save_wallet(w)
    log.info(f"[WALLET] Deposited ${amount:.2f}. New balance: ${w['balance']:.2f}")
    return w['balance']

def deduct(amount: float, ticker: str):
    w = load_wallet()
    if w['balance'] < amount:
        log.warning(f"[WALLET] Insufficient funds for {ticker}. Need ${amount:.2f}, have ${w['balance']:.2f}. Skipping.")
        return False
    w['balance'] -= amount
    w['total_spent'] += amount
    w['transactions'].append({
        'type': 'trade',
        'ticker': ticker,
        'amount': amount,
        'balance': w['balance'],
        'timestamp': datetime.now().isoformat()
    })
    save_wallet(w)
    log.info(f"[WALLET] Spent ${amount:.2f} on {ticker}. Remaining: ${w['balance']:.2f}")
    return True

def refund(amount: float, ticker: str, reason: str = 'Trade failed'):
    w = load_wallet()
    w['balance'] += amount
    w['transactions'].append({
        'type': 'refund',
        'ticker': ticker,
        'amount': amount,
        'balance': w['balance'],
        'reason': reason,
        'timestamp': datetime.now().isoformat()
    })
    save_wallet(w)
    log.info(f"[WALLET] Refunded ${amount:.2f} from {ticker}. Balance: ${w['balance']:.2f}")

def get_summary():
    w = load_wallet()
    return {
        'balance': round(w['balance'], 2),
        'total_deposited': round(w['total_deposited'], 2),
        'total_spent': round(w['total_spent'], 2),
        'transactions': w['transactions'][-50:]
    }
