Evelyn V3 Power Pack

Included in this build

1. Alpaca paper trading support carried forward
2. Strategy engine with RSI plus moving average signals
3. Dip buy boost logic
4. Risk controls for max trade amount, max trades per day, and max daily spend
5. Live positions and P and L API
6. Backtest API with a simple strategy simulator
7. Telegram alert support
8. Bigger Evelyn AI header using the new logo
9. Test alert endpoint

Main new files

alerts.py
strategy_engine.py
backtester.py

Important notes

1. Use paper trading first
2. Telegram alerts require a bot token and chat ID
3. Backtesting is a simple built in simulator, not a professional execution model
4. Strategy signals are designed as a practical starter layer

Install

Rebuild the Docker image after replacing the files
