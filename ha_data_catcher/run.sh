#!/usr/bin/env bash
set -e

echo "[Data Collector] Starting Home Assistant Data Collector Add-on..."

# Launch the python application in unbuffered mode so logs appear instantly
exec python3 -u /app/main.py
