Evelyn public GitHub package

This package is prepared for public code sharing.

What was removed
1. No live data folder is included.
2. No login files are included.
3. No bot config with real values is included.
4. No logs are included.
5. No secrets are included.

Before you publish
1. Set real secrets only on your server in a local env file or in app settings.
2. Keep port 5000 off the public internet unless you use a VPN or stronger access control.
3. Use a long Flask secret.
4. Rotate any keys you may have typed into test files in the past.

Recommended files to keep private
1. data/bot_config.json
2. data/bot_config.backup.json
3. data/users.json
4. data/auth.json
5. logs/
6. any .env file with real values

Quick Git steps
1. git init
2. git add .
3. git commit -m "Initial public Evelyn release"
4. git branch -M main
5. git remote add origin YOUR_REPO_URL
6. git push -u origin main
