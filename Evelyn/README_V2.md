# Evelyn v2

This version fixes the most fragile parts of the original bot.

## What changed
- one shared config source for both the dashboard and the bot
- no more rewriting `robinbot.py` when you save settings
- fixed `run now` to call `robinbot.run_dca_cycle()`
- shared data folder for config, wallet, logs, and monitor files
- optional environment variables for secrets so passwords do not have to live in JSON
- Docker compose updated for a cleaner persistent path layout

## Important warning
This project still uses unofficial Robinhood automation. Use dry run first and be careful with real money.

## Run on a regular PC
```bash
pip install -r requirements.txt
python server.py
```

## Run with Docker Compose
```bash
docker compose up -d --build
```

## Optional environment variables
- `EVELYN_RH_USERNAME`
- `EVELYN_RH_PASSWORD`
- `EVELYN_EMAIL_SENDER`
- `EVELYN_EMAIL_PASSWORD`
- `EVELYN_EMAIL_RECIPIENT`

## Notes
The dashboard still supports saving credentials in the config file for convenience, but environment variables override saved values when present.


Alpaca update

This build adds working Alpaca credential save, connection test, account balance, and DCA buy support through the main bot when broker is set to Alpaca.


## V3 Power Pack

This build adds Alpaca paper trading support, strategy signals, live positions and P and L, Telegram alerts, backtesting, and basic risk controls.
