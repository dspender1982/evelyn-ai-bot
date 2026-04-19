Evelyn Security Pack

What this update adds

1. Dashboard login page with session protection
2. Admin password hash support
3. Local network only mode by default
4. Live trading lock and unlock code
5. Audit log endpoint and audit file
6. Secure response headers and no store cache policy
7. Login rate limiting for repeated failures

How to use it

1. Replace your current app folder with this build
2. Rebuild Docker
3. Open the dashboard
4. On the first login, use the admin username and create your password
5. In Security Center, set a live unlock code
6. Keep dry run on until you are ready

Files of interest

app_config.py
server.py
templates/login.html
robinbot.py

Security note

This is a strong step up from plain text only access, but you should still keep the app on your local network or behind a VPN.


Hotfixes included in this bundle:
1. Fixed server.py audit log syntax error.
2. Updated login.html with stronger login error handling.
