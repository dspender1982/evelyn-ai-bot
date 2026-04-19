"""Evelyn Web UI with auth, audit logging, and local only protection."""

from flask import Flask, jsonify, request, render_template, session, redirect, url_for
import json
import os
import signal
import subprocess
import threading
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from app_config import (
    CONFIG_FILE, DEFAULT_CONFIG, LOG_FILE, BASE_DIR, DATA_DIR, AUDIT_LOG_FILE,
    load_config, save_config, sanitized_config, ensure_dirs,
    set_admin_password, verify_admin_password, set_live_unlock_code, verify_live_unlock_code
)

ensure_dirs()
app = Flask(__name__)
app.secret_key = os.environ.get('EVELYN_FLASK_SECRET', 'change_this_secret_now')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
BOT_PROCESS = None
BOT_LOCK = threading.Lock()
LOGIN_ATTEMPTS = {}


def audit_log(action, detail=''):
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ip = request.headers.get('X-Forwarded-For', request.remote_addr) if request else 'local'
    user = session.get('user', 'anonymous') if session else 'anonymous'
    line = f"{datetime.now().isoformat()} | user={user} | ip={ip} | action={action} | {detail}\n"
    with open(AUDIT_LOG_FILE, 'a') as f:
        f.write(line)


def active_broker(cfg=None):
    cfg = cfg or load_config()
    return (cfg.get('broker') or 'robinhood').lower()


def is_bot_running():
    global BOT_PROCESS
    return BOT_PROCESS is not None and BOT_PROCESS.poll() is None


def tail_log(n=60):
    if not Path(LOG_FILE).exists():
        return []
    with open(LOG_FILE) as f:
        return [line.rstrip() for line in f.readlines()[-n:]]


def is_private_ip(ip):
    if not ip:
        return False
    if ip in {'127.0.0.1', '::1'}:
        return True
    if ip.startswith('10.') or ip.startswith('192.168.'):
        return True
    if ip.startswith('172.'):
        try:
            second = int(ip.split('.')[1])
            return 16 <= second <= 31
        except Exception:
            return False
    return False


def current_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '')


def is_session_valid(cfg=None):
    cfg = cfg or load_config()
    if not session.get('logged_in'):
        return False
    ts = session.get('last_seen')
    if not ts:
        return False
    try:
        last_seen = datetime.fromisoformat(ts)
    except Exception:
        return False
    timeout_minutes = int(cfg.get('session_timeout_minutes', 120) or 120)
    if datetime.now() - last_seen > timedelta(minutes=timeout_minutes):
        session.clear()
        return False
    session['last_seen'] = datetime.now().isoformat()
    return True


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        cfg = load_config()
        if cfg.get('auth_enabled', True) and not is_session_valid(cfg):
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'msg': 'Login required'}), 401
            return redirect(url_for('login_page'))
        return fn(*args, **kwargs)
    return wrapper


@app.before_request
def security_gate():
    cfg = load_config()
    public_paths = {'/login', '/api/login'}
    if request.path.startswith('/static/'):
        return None
    if not cfg.get('allow_remote_access', False) and not is_private_ip(current_ip()):
        audit_log('remote_blocked', request.path)
        return 'Remote access blocked by Evelyn security settings.', 403
    if request.path in public_paths:
        return None
    if cfg.get('auth_enabled', True):
        if not is_session_valid(cfg):
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'msg': 'Login required'}), 401
            return redirect(url_for('login_page'))
    return None


@app.after_request
def secure_headers(resp):
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Referrer-Policy'] = 'same-origin'
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def get_positions_for_active_broker(cfg=None):
    cfg = cfg or load_config()
    broker = active_broker(cfg)
    if broker == 'alpaca':
        import alpaca_adapter as alp
        return alp.get_positions(cfg)
    try:
        import robin_stocks.robinhood as rh
        if not cfg.get('rh_username') or not cfg.get('rh_password'):
            return []
        rh.login(cfg['rh_username'], cfg['rh_password'])
        holdings = rh.account.build_holdings() or {}
        out = []
        for symbol, data in holdings.items():
            out.append({
                'symbol': symbol,
                'qty': float(data.get('quantity', 0) or 0),
                'market_value': float(data.get('equity', 0) or 0),
                'unrealized_pl': float(data.get('equity_change', 0) or 0),
                'unrealized_plpc': float(data.get('percent_change', 0) or 0),
            })
        rh.logout()
        return out
    except Exception:
        return []


@app.route('/login')
def login_page():
    cfg = load_config()
    return render_template('login.html', cfg=sanitized_config(cfg))


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    audit_log('logout')
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/api/login', methods=['POST'])
def api_login():
    cfg = load_config()
    ip = current_ip()
    state = LOGIN_ATTEMPTS.get(ip, {'count': 0, 'until': datetime.min})
    if state['until'] > datetime.now():
        return jsonify({'ok': False, 'msg': 'Too many login attempts. Wait a few minutes and try again.'}), 429

    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not cfg.get('admin_password_hash') and not os.environ.get('EVELYN_ADMIN_PASSWORD_HASH'):
        if username == cfg.get('admin_username', 'admin') and password:
            set_admin_password(password)
            session['logged_in'] = True
            session['user'] = username
            session['last_seen'] = datetime.now().isoformat()
            audit_log('login_bootstrap', 'Initial admin password created')
            return jsonify({'ok': True, 'bootstrap': True})
        return jsonify({'ok': False, 'msg': 'Set an admin password by logging in with the admin username and a new password.'}), 400

    if username == cfg.get('admin_username', 'admin') and verify_admin_password(password, cfg):
        LOGIN_ATTEMPTS[ip] = {'count': 0, 'until': datetime.min}
        session['logged_in'] = True
        session['user'] = username
        session['last_seen'] = datetime.now().isoformat()
        audit_log('login_success')
        return jsonify({'ok': True})

    count = state['count'] + 1
    lock_until = datetime.now() + timedelta(minutes=5) if count >= 5 else datetime.min
    LOGIN_ATTEMPTS[ip] = {'count': count, 'until': lock_until}
    audit_log('login_failed', f'count={count}')
    return jsonify({'ok': False, 'msg': 'Invalid login'}), 401


@app.route('/api/security/status', methods=['GET'])
@login_required
def api_security_status():
    cfg = load_config()
    return jsonify({
        'ok': True,
        'auth_enabled': cfg.get('auth_enabled', True),
        'allow_remote_access': cfg.get('allow_remote_access', False),
        'live_trading_unlocked': cfg.get('live_trading_unlocked', False),
        'admin_username': cfg.get('admin_username', 'admin'),
        'admin_password_set': bool(cfg.get('admin_password_hash') or os.environ.get('EVELYN_ADMIN_PASSWORD_HASH')),
        'live_unlock_code_set': bool(cfg.get('live_unlock_code_hash') or os.environ.get('EVELYN_LIVE_UNLOCK_CODE_HASH')),
        'session_timeout_minutes': cfg.get('session_timeout_minutes', 120),
    })


@app.route('/api/security/config', methods=['POST'])
@login_required
def api_security_config():
    data = request.json or {}
    cfg = load_config()
    allowed = ['auth_enabled', 'allow_remote_access', 'session_timeout_minutes']
    for key in allowed:
        if key in data:
            cfg[key] = data[key]
    if data.get('new_admin_username'):
        cfg['admin_username'] = str(data['new_admin_username']).strip()
    save_config(cfg)
    if data.get('new_admin_password'):
        set_admin_password(str(data['new_admin_password']))
    if data.get('new_live_unlock_code'):
        set_live_unlock_code(str(data['new_live_unlock_code']))
    audit_log('security_config_updated')
    return jsonify({'ok': True})


@app.route('/api/security/unlock_live', methods=['POST'])
@login_required
def api_unlock_live():
    data = request.json or {}
    code = data.get('code') or ''
    cfg = load_config()
    if not verify_live_unlock_code(code, cfg):
        audit_log('live_unlock_failed')
        return jsonify({'ok': False, 'msg': 'Wrong live unlock code'}), 403
    cfg['live_trading_unlocked'] = True
    save_config(cfg)
    audit_log('live_unlock_success')
    return jsonify({'ok': True, 'msg': 'Live trading unlocked'})


@app.route('/api/security/lock_live', methods=['POST'])
@login_required
def api_lock_live():
    cfg = load_config()
    cfg['live_trading_unlocked'] = False
    save_config(cfg)
    audit_log('live_lock_enabled')
    return jsonify({'ok': True})


@app.route('/api/wallet', methods=['GET'])
@login_required
def get_wallet():
    import wallet as W
    return jsonify(W.get_summary())


@app.route('/api/wallet/deposit', methods=['POST'])
@login_required
def wallet_deposit():
    import wallet as W
    data = request.json or {}
    amount = float(data.get('amount', 0))
    note = data.get('note', 'Web UI deposit')
    if amount <= 0:
        return jsonify({'ok': False, 'msg': 'Amount must be positive'})
    balance = W.deposit(amount, note)
    audit_log('wallet_deposit', f'amount={amount}')
    return jsonify({'ok': True, 'balance': balance})


@app.route('/api/wallet/reset', methods=['POST'])
@login_required
def wallet_reset():
    import wallet as W
    Path(W.WALLET_FILE).unlink(missing_ok=True)
    audit_log('wallet_reset')
    return jsonify({'ok': True})


@app.route('/api/monitors', methods=['GET'])
@login_required
def get_monitors():
    import monitors as MON
    return jsonify(MON.get_monitors_summary())


@app.route('/api/monitors', methods=['POST'])
@login_required
def save_monitors():
    import monitors as MON
    data = request.json or {}
    m = MON.load_monitors()
    for key in ['earnings_alerts', 'volume_alerts', 'volume_threshold', 'insider_alerts']:
        if key in data:
            m[key] = data[key]
    MON.save_monitors(m)
    audit_log('monitors_updated')
    return jsonify({'ok': True})


@app.route('/api/monitors/price-target', methods=['POST'])
@login_required
def set_price_target():
    import monitors as MON
    data = request.json or {}
    ticker = data.get('ticker', '').upper()
    target = float(data.get('target', 0))
    direction = data.get('direction', 'above')
    if not ticker or target <= 0:
        return jsonify({'ok': False, 'msg': 'Invalid ticker or target price'})
    MON.set_price_target(ticker, target, direction)
    audit_log('price_target_set', f'{ticker} {direction} {target}')
    return jsonify({'ok': True})


@app.route('/api/monitors/price-target/<ticker>', methods=['DELETE'])
@login_required
def delete_price_target(ticker):
    import monitors as MON
    MON.remove_price_target(ticker)
    audit_log('price_target_deleted', ticker)
    return jsonify({'ok': True})


@app.route('/api/validate-ticker')
@login_required
def validate_ticker():
    import yfinance as yf
    ticker = request.args.get('ticker', '').upper().strip()
    if not ticker:
        return jsonify({'valid': False, 'msg': 'No ticker provided'})
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = float(info.last_price)
        if price and price > 0:
            name = getattr(t, 'info', {}).get('longName', ticker) if hasattr(t, 'info') else ticker
            return jsonify({'valid': True, 'ticker': ticker, 'name': name, 'price': round(price, 2)})
        return jsonify({'valid': False, 'msg': f'"{ticker}" is not a recognised stock symbol'})
    except Exception:
        return jsonify({'valid': False, 'msg': f'"{ticker}" could not be verified'})


@app.route('/api/chart-data')
@login_required
def get_chart_data():
    import yfinance as yf
    ticker = request.args.get('ticker', 'AAPL')
    range_ = request.args.get('range', '1mo')
    try:
        period = {'5d': '5d', '1mo': '1mo', '3mo': '3mo', '1y': '1y'}.get(range_, '1mo')
        interval = '1h' if range_ == '5d' else '1d'
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval=interval)
        if hist.empty:
            return json.dumps({'error': 'No data'}), 500, {'Content-Type': 'application/json'}
        closes = [round(float(c), 2) for c in hist['Close']]
        labels = [str(i.strftime('%H:%M' if interval == '1h' else '%b %d')) for i in hist.index]
        info = t.fast_info
        return json.dumps({
            'ticker': ticker,
            'closes': closes,
            'labels': labels,
            'current_price': closes[-1] if closes else 0,
            'prev_close': closes[-2] if len(closes) > 1 else closes[-1] if closes else 0,
            'high_52w': round(float(getattr(info, 'year_high', max(closes))), 2),
            'low_52w': round(float(getattr(info, 'year_low', min(closes))), 2),
        }), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({'error': str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/api/quotes')
@login_required
def get_quotes():
    import yfinance as yf
    symbols = request.args.get('symbols', '')
    if not symbols:
        return jsonify({})
    result = {}
    try:
        tickers = yf.Tickers(symbols.replace(',', ' '))
        for sym in symbols.split(','):
            sym = sym.strip().upper()
            try:
                info = tickers.tickers[sym].fast_info
                price = round(float(info.last_price), 2)
                prev = round(float(info.previous_close), 2)
                chg = round(price - prev, 2)
                pct = round((chg / prev) * 100, 2) if prev else 0
                result[sym] = {'price': price, 'change': chg, 'pct': pct}
            except Exception:
                pass
    except Exception:
        pass
    return jsonify(result)


@app.route('/api/ai-pick', methods=['POST'])
@login_required
def run_ai_pick():
    try:
        import ai_picker as AI
        cfg = load_config()
        picks = AI.pick_stocks(num_stocks=cfg.get('ai_num_stocks', 5))
        AI.save_picks(picks)
        audit_log('ai_pick_run', ','.join([p.get('ticker','') for p in picks]))
        return jsonify({'ok': True, 'picks': picks})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})


@app.route('/api/ai-picks', methods=['GET'])
@login_required
def get_ai_picks():
    try:
        import ai_picker as AI
        data = AI.load_picks()
        return jsonify(data if data else {'picks': [], 'timestamp': ''})
    except Exception:
        return jsonify({'picks': [], 'timestamp': ''})


@app.route('/api/test-connection', methods=['POST'])
@login_required
def test_connection():
    cfg = load_config()
    broker = active_broker(cfg)
    if broker == 'alpaca':
        try:
            import alpaca_adapter as alp
            data = alp.test_connection(cfg)
            audit_log('broker_test', f'{broker} ok={data.get("ok")}')
            return jsonify(data)
        except Exception as e:
            audit_log('broker_test_failed', f'{broker} {e}')
            return jsonify({'ok': False, 'msg': f'Alpaca connection failed: {e}'})
    if broker == 'webull':
        return jsonify({'ok': False, 'msg': 'Webull is not wired yet in this build.'})
    try:
        import robin_stocks.robinhood as rh
        if not cfg.get('rh_username') or not cfg.get('rh_password'):
            return jsonify({'ok': False, 'msg': 'No credentials saved. Enter your email and password above and save first.'})
        rh.login(cfg['rh_username'], cfg['rh_password'])
        profile = rh.profiles.load_portfolio_profile()
        account = rh.profiles.load_account_profile()
        equity = round(float(profile.get('equity', 0) or 0), 2)
        cash = round(float(account.get('buying_power', 0) or 0), 2)
        holdings = rh.account.build_holdings()
        rh.logout()
        audit_log('broker_test', f'robinhood ok positions={len(holdings)}')
        return jsonify({'ok': True, 'equity': equity, 'cash': cash, 'num_pos': len(holdings), 'msg': 'Connected successfully!'})
    except Exception as e:
        err = str(e).lower()
        if any(x in err for x in ['challenge', '2fa', 'verification', 'mfa']):
            msg = 'Robinhood asked for 2FA verification. Complete that challenge in the broker app, then test again.'
        elif any(x in err for x in ['password', 'credential', 'invalid', 'unauthorized']):
            msg = 'Wrong email or password. Double check your Robinhood credentials.'
        elif any(x in err for x in ['network', 'connection', 'timeout']):
            msg = 'Network error. Check your server internet connection.'
        else:
            msg = f'Connection failed: {e}'
        audit_log('broker_test_failed', msg)
        return jsonify({'ok': False, 'msg': msg})


@app.route('/api/broker-balance')
@login_required
def broker_balance():
    try:
        import wallet as W
        cfg = load_config()
        broker = active_broker(cfg)
        if broker == 'alpaca':
            import alpaca_adapter as alp
            data = alp.get_balance(cfg)
            data['ok'] = True
            data['wallet'] = round(W.get_balance(), 2)
            data['source'] = 'Alpaca'
            return jsonify(data)
        if broker == 'webull':
            return jsonify({'ok': False, 'msg': 'Webull is not wired yet in this build.'})
        import robin_stocks.robinhood as rh
        if not cfg.get('rh_username') or not cfg.get('rh_password'):
            return jsonify({'ok': False, 'msg': 'No Robinhood credentials set'})
        rh.login(cfg['rh_username'], cfg['rh_password'])
        portfolio = rh.profiles.load_portfolio_profile()
        account = rh.profiles.load_account_profile()
        equity = float(portfolio.get('equity', 0) or 0)
        prev = float(portfolio.get('adjusted_equity_previous_close', equity) or equity)
        day_chg = round(equity - prev, 2)
        day_pct = round((day_chg / prev * 100), 2) if prev else 0
        cash = float(account.get('buying_power', 0) or 0)
        rh.logout()
        return jsonify({'ok': True, 'equity': round(equity, 2), 'cash': round(cash, 2), 'day_chg': day_chg, 'day_pct': day_pct, 'wallet': round(W.get_balance(), 2), 'source': 'Robinhood'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})


@app.route('/api/positions', methods=['GET'])
@login_required
def api_positions():
    cfg = load_config()
    try:
        positions = get_positions_for_active_broker(cfg)
        total_value = round(sum(float(p.get('market_value', 0) or 0) for p in positions), 2)
        total_pl = round(sum(float(p.get('unrealized_pl', 0) or 0) for p in positions), 2)
        return jsonify({'ok': True, 'positions': positions, 'total_value': total_value, 'total_pl': total_pl})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e), 'positions': [], 'total_value': 0, 'total_pl': 0})


@app.route('/api/strategy-scan', methods=['GET'])
@login_required
def api_strategy_scan():
    import strategy_engine as SE
    cfg = load_config()
    symbols = request.args.get('symbols', '')
    symbols = [s.strip().upper() for s in symbols.split(',') if s.strip()] or list((cfg.get('dca_stocks') or {}).keys())
    results = []
    for symbol in symbols[:20]:
        try:
            results.append(SE.evaluate_symbol(symbol, cfg))
        except Exception as e:
            results.append({'symbol': symbol, 'action': 'ERROR', 'score': -99, 'reason': str(e), 'price': 0})
    return jsonify({'ok': True, 'results': results})


@app.route('/api/backtest', methods=['POST'])
@login_required
def api_backtest():
    import backtester as BT
    cfg = load_config()
    data = request.json or {}
    symbol = (data.get('symbol') or 'SPY').upper()
    start = data.get('start') or cfg.get('backtest_start') or '2024-01-01'
    end = data.get('end') or cfg.get('backtest_end') or ''
    starting_cash = float(data.get('starting_cash', 10000) or 10000)
    trade_size = float(data.get('trade_size', cfg.get('max_trade_amount', 500)) or 500)
    try:
        return jsonify(BT.run_backtest(symbol, start, end, starting_cash, trade_size, cfg))
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})


@app.route('/api/test-alert', methods=['POST'])
@login_required
def api_test_alert():
    import alerts as A
    from robinbot import send_email
    cfg = load_config()
    A.send_alert('Evelyn test alert', 'Your alert system is working.', email_func=send_email, cfg=cfg)
    audit_log('test_alert_sent')
    return jsonify({'ok': True, 'msg': 'Test alert sent. Check email, Telegram, and alerts.log.'})


@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/api/config', methods=['GET'])
@login_required
def get_config():
    return jsonify(sanitized_config(load_config()))


@app.route('/api/config', methods=['POST'])
@login_required
def set_config():
    data = request.json or {}
    cfg = load_config()
    for key in DEFAULT_CONFIG:
        if key in data:
            if key in {'admin_password_hash', 'live_unlock_code_hash'}:
                continue
            if 'password' in key and data[key] == '':
                continue
            if key == 'dry_run' and data[key] is False and not cfg.get('live_trading_unlocked', False):
                return jsonify({'ok': False, 'msg': 'Live trading is locked. Unlock it first.'}), 403
            cfg[key] = data[key]
    save_config(cfg)
    audit_log('config_updated')
    return jsonify({'ok': True})


@app.route('/api/status')
@login_required
def status():
    cfg = load_config()
    return jsonify({
        'running': is_bot_running(),
        'dry_run': cfg['dry_run'],
        'frequency': cfg['buy_frequency'],
        'stocks': cfg['dca_stocks'],
        'max_spend': cfg['max_spend'],
        'broker': cfg.get('broker', 'robinhood'),
        'strategy_enabled': cfg.get('strategy_enabled', True),
        'live_trading_unlocked': cfg.get('live_trading_unlocked', False),
    })


@app.route('/api/logs')
@login_required
def logs():
    return jsonify({'lines': tail_log()})


@app.route('/api/audit-logs')
@login_required
def audit_logs():
    if not Path(AUDIT_LOG_FILE).exists():
        return jsonify({'lines': []})
    with open(AUDIT_LOG_FILE) as f:
        lines = [line.rstrip() for line in f.readlines()[-100:]]
    return jsonify({'lines': lines})


@app.route('/api/start', methods=['POST'])
@login_required
def start_bot():
    global BOT_PROCESS
    with BOT_LOCK:
        if is_bot_running():
            return jsonify({'ok': False, 'msg': 'Bot already running'})
        with open(LOG_FILE, 'a') as log_handle:
            BOT_PROCESS = subprocess.Popen(['python', '-u', 'robinbot.py'], cwd=str(BASE_DIR), stdout=log_handle, stderr=subprocess.STDOUT)
    audit_log('bot_started', f'pid={BOT_PROCESS.pid}')
    return jsonify({'ok': True, 'pid': BOT_PROCESS.pid})


@app.route('/api/stop', methods=['POST'])
@login_required
def stop_bot():
    global BOT_PROCESS
    with BOT_LOCK:
        if not is_bot_running():
            return jsonify({'ok': False, 'msg': 'Bot not running'})
        BOT_PROCESS.send_signal(signal.SIGTERM)
        BOT_PROCESS.wait(timeout=5)
        BOT_PROCESS = None
    audit_log('bot_stopped')
    return jsonify({'ok': True})


@app.route('/api/run-now', methods=['POST'])
@login_required
def run_now():
    def _run():
        import robinbot
        robinbot.run_dca_cycle()
    threading.Thread(target=_run, daemon=True).start()
    audit_log('run_now_triggered')
    return jsonify({'ok': True})


if __name__ == '__main__':
    print('Evelyn UI running at http://0.0.0.0:5000')
    app.run(host='0.0.0.0', port=5000, debug=False)
