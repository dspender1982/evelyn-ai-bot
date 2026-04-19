from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

from app_config import DATA_DIR, load_config

ALERT_LOG = Path(DATA_DIR) / 'alerts.log'


def log_alert(message: str):
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ALERT_LOG.open('a', encoding='utf-8') as f:
        f.write(f"{datetime.now().isoformat()} | {message}\n")


def send_telegram(message: str, cfg: Optional[dict] = None) -> bool:
    cfg = cfg or load_config()
    if not cfg.get('telegram_enabled'):
        return False
    token = (cfg.get('telegram_bot_token') or '').strip()
    chat_id = (cfg.get('telegram_chat_id') or '').strip()
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({'chat_id': chat_id, 'text': message}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def send_alert(subject: str, body: str, email_func=None, cfg: Optional[dict] = None):
    cfg = cfg or load_config()
    msg = f"{subject}\n\n{body}".strip()
    log_alert(msg)
    if email_func:
        try:
            email_func(subject, body)
        except Exception:
            pass
    send_telegram(msg, cfg)
