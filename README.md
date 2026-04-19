Public GitHub safe build

Use .env.example as a guide and keep real secrets only on your server.

# Robinhood DCA Bot — Web UI Setup

## Files
- `robinhood_dca_bot.py` — The trading bot
- `server.py`            — Flask web server (serves the UI + API)
- `templates/index.html` — Dashboard web UI
- `requirements.txt`     — Python dependencies
- `Dockerfile`           — Container build
- `docker-compose.yml`   — TrueNAS app definition

---

## Deploying on TrueNAS SCALE

### Step 1 — Copy files to your pool
Put all files in a folder on your TrueNAS pool:
  /mnt/tank/dca-bot/

### Step 2 — Edit docker-compose.yml
Change 'your-pool' to your actual pool name.
Set your timezone (TZ=America/New_York etc.)

### Step 3 — Deploy via SSH
  cd /mnt/tank/dca-bot
  docker compose up -d --build

### Step 4 — Open the dashboard
In your browser on your local network, go to:
  http://your-truenas-ip:5000

Find your TrueNAS IP in: TrueNAS UI → Network → Global Configuration

---

## Using the Dashboard

1. Go to the Stocks tab — add/remove stocks and set $ per cycle
2. Go to Schedule — choose daily/weekly/monthly and toggle dry run
3. Go to Email Alerts — enter your Gmail app password
4. Click Save on each page
5. Go to Dashboard → click Start Bot
6. Watch the Logs tab for live activity

---

## Accessing from anywhere on your network
The UI runs on port 5000. Any device on your home network can access it:
  http://192.168.1.x:5000   (replace with your TrueNAS IP)

---

## 💻 Running on a Regular PC (No Docker)

Evelyn automatically detects whether it's running in Docker or on a regular PC and adjusts file paths accordingly. No configuration needed.

### Windows

1. Install Python from https://python.org (check "Add to PATH" during install)
2. Copy all Evelyn files to a folder e.g. `C:\Evelyn\`
3. Double click `setup.py` to install dependencies (or run in Command Prompt)
4. Double click `start.bat` to launch Evelyn
5. Open browser to `http://localhost:5000`

### Mac

```bash
cd ~/Evelyn
python3 setup.py
python3 server.py
```

### Linux / Ubuntu

```bash
cd ~/evelyn
python3 setup.py
python3 server.py
```

Then open `http://localhost:5000` in your browser.

### Keeping Evelyn running on a PC

**Windows** — Create a Scheduled Task to run `start.bat` at login.

**Mac** — Add to Login Items or create a launchd plist.

**Linux** — Add to crontab:
```bash
@reboot cd ~/evelyn && python3 server.py &
```

### File structure on PC

All settings are saved in the same folder as the scripts:
```
Evelyn/
├── server.py
├── robinbot.py
├── advisor.py
├── ai_picker.py
├── smart_trader.py
├── wallet.py
├── monitors.py
├── setup.py
├── start.bat          ← Windows launcher
├── start.sh           ← Mac/Linux launcher
├── requirements.txt
├── templates/
│   └── index.html
└── static/
    └── evelyn_logo.png
```

Settings files are created automatically when you first run Evelyn:
- `bot_config.json` — your stocks, schedule, email settings
- `wallet.json` — your wallet balance and history
- `monitors.json` — your price targets and monitor settings
- `evelyn.log` — activity log

