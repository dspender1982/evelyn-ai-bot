"""
Evelyn Setup Script
===================
Run this once to install all dependencies.
Works on Windows, Mac and Linux.

Usage:
    python setup.py
    python3 setup.py
"""
import subprocess
import sys
import os

print("=" * 50)
print("  Evelyn — Setup")
print("=" * 50)
print()

# Install dependencies
print("Installing dependencies...")
subprocess.check_call([
    sys.executable, "-m", "pip", "install",
    "flask", "robin_stocks", "schedule", "yfinance"
])

print()
print("=" * 50)
print("Setup complete!")
print()
print("To start Evelyn:")
if sys.platform == "win32":
    print("  python server.py")
else:
    print("  python3 server.py")
print()
print("Then open your browser to:")
print("  http://localhost:5000")
print("=" * 50)
