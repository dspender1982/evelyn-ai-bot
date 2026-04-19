import json
import os
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
IN_DOCKER = Path('/.dockerenv').exists() or bool(os.environ.get('IN_DOCKER'))
DATA_DIR = Path(os.environ.get('EVELYN_DATA_DIR', '/app/data' if IN_DOCKER else str(BASE_DIR / 'data')))
STATIC_DIR = Path(os.environ.get('EVELYN_STATIC_DIR', '/app/static' if IN_DOCKER else str(BASE_DIR / 'static')))
LOG_FILE = DATA_DIR / 'evelyn.log'
CONFIG_FILE = DATA_DIR / 'bot_config.json'
AUDIT_LOG_FILE = DATA_DIR / 'audit.log'

DEFAULT_CONFIG = {
    'rh_username': '',
    'rh_password': '',
    'dca_stocks': {'AAPL': 10, 'MSFT': 10, 'SPY': 20},
    'buy_frequency': 'weekly',
    'max_spend': 100,
    'dry_run': True,
    'email_enabled': True,
    'email_sender': '',
    'email_password': '',
    'email_recipient': '',
    'profit_target_on': True,
    'profit_target_pct': 20.0,
    'stop_loss_on': True,
    'stop_loss_pct': 10.0,
    'news_check_on': True,
    'news_min_score': -2,
    'monitor_interval': 60,
    'broker': 'robinhood',
    'alpaca_key': '',
    'alpaca_secret': '',
    'alpaca_paper': True,
    'ai_mode': False,
    'ai_num_stocks': 5,
    'ai_dollar_each': 20,
    'alert_only': True,
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'use_wallet': True,
    'telegram_enabled': False,
    'telegram_bot_token': '',
    'telegram_chat_id': '',
    'strategy_enabled': True,
    'strategy_mode': 'hybrid',
    'strategy_rsi_period': 14,
    'strategy_rsi_buy_below': 35,
    'strategy_ma_short': 20,
    'strategy_ma_long': 50,
    'dip_buy_enabled': True,
    'dip_buy_pct': 5.0,
    'dip_buy_multiplier': 2.0,
    'max_trade_amount': 50,
    'max_trades_per_day': 5,
    'max_daily_spend': 250,
    'backtest_start': '2024-01-01',
    'backtest_end': '',
    'auth_enabled': True,
    'admin_username': 'admin',
    'admin_password_hash': '',
    'allow_remote_access': False,
    'live_trading_unlocked': False,
    'live_unlock_code_hash': '',
    'session_timeout_minutes': 120,
}

SECRET_ENV_MAP = {
    'rh_username': 'EVELYN_RH_USERNAME',
    'rh_password': 'EVELYN_RH_PASSWORD',
    'email_sender': 'EVELYN_EMAIL_SENDER',
    'email_password': 'EVELYN_EMAIL_PASSWORD',
    'email_recipient': 'EVELYN_EMAIL_RECIPIENT',
    'alpaca_key': 'EVELYN_ALPACA_KEY',
    'alpaca_secret': 'EVELYN_ALPACA_SECRET',
    'telegram_bot_token': 'EVELYN_TELEGRAM_BOT_TOKEN',
    'telegram_chat_id': 'EVELYN_TELEGRAM_CHAT_ID',
    'admin_password_hash': 'EVELYN_ADMIN_PASSWORD_HASH',
    'live_unlock_code_hash': 'EVELYN_LIVE_UNLOCK_CODE_HASH',
}

def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

def load_config():
    ensure_dirs()
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open() as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                cfg.update(loaded)
    for key, env_name in SECRET_ENV_MAP.items():
        if os.environ.get(env_name):
            cfg[key] = os.environ[env_name]
    return cfg

def save_config(cfg: dict):
    ensure_dirs()
    merged = DEFAULT_CONFIG.copy()
    merged.update(cfg or {})
    with CONFIG_FILE.open('w') as f:
        json.dump(merged, f, indent=2)
    return merged

def set_admin_password(password: str):
    cfg = load_config()
    cfg['admin_password_hash'] = generate_password_hash(password)
    save_config(cfg)
    return True

def verify_admin_password(password: str, cfg=None):
    cfg = cfg or load_config()
    pwd_hash = cfg.get('admin_password_hash') or os.environ.get('EVELYN_ADMIN_PASSWORD_HASH', '')
    if not pwd_hash:
        return False
    return check_password_hash(pwd_hash, password)

def set_live_unlock_code(code: str):
    cfg = load_config()
    cfg['live_unlock_code_hash'] = generate_password_hash(code)
    save_config(cfg)
    return True

def verify_live_unlock_code(code: str, cfg=None):
    cfg = cfg or load_config()
    code_hash = cfg.get('live_unlock_code_hash') or os.environ.get('EVELYN_LIVE_UNLOCK_CODE_HASH', '')
    if not code_hash:
        return False
    return check_password_hash(code_hash, code)

def sanitized_config(cfg: dict):
    blocked_exact = {
        'rh_password', 'email_password', 'alpaca_secret', 'telegram_bot_token',
        'admin_password_hash', 'live_unlock_code_hash'
    }
    safe = {k: v for k, v in cfg.items() if k not in blocked_exact and 'password' not in k}
    safe['rh_password_set'] = bool(cfg.get('rh_password') or os.environ.get('EVELYN_RH_PASSWORD'))
    safe['email_password_set'] = bool(cfg.get('email_password') or os.environ.get('EVELYN_EMAIL_PASSWORD'))
    safe['alpaca_secret_set'] = bool(cfg.get('alpaca_secret') or os.environ.get('EVELYN_ALPACA_SECRET'))
    safe['telegram_bot_token_set'] = bool(cfg.get('telegram_bot_token') or os.environ.get('EVELYN_TELEGRAM_BOT_TOKEN'))
    safe['admin_password_set'] = bool(cfg.get('admin_password_hash') or os.environ.get('EVELYN_ADMIN_PASSWORD_HASH'))
    safe['live_unlock_code_set'] = bool(cfg.get('live_unlock_code_hash') or os.environ.get('EVELYN_LIVE_UNLOCK_CODE_HASH'))
    return safe
