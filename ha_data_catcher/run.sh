#!/usr/bin/env bash
set -e

echo "[Data Collector] Starting Home Assistant Data Collector Add-on..."

if [ -f /firebase-service-account.b64 ]; then
    base64 -d /firebase-service-account.b64 > /firebase-service-account.json
fi

# Launch the python application in unbuffered mode so logs appear instantly
exec python3 -u /app/main.py
