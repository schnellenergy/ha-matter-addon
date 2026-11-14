#!/usr/bin/env bash
set -e

echo "[Data Collector] Starting Home Assistant Data Collector Add-on..."

# Firebase credentials come from the add-on options, never from the image.
if [ -f /data/options.json ]; then
    FB_CRED=$(jq -r '.firebase_credentials_b64 // empty' /data/options.json)
    if [ -n "$FB_CRED" ]; then
        printf '%s' "$FB_CRED" | base64 -d > /firebase-service-account.json
        chmod 600 /firebase-service-account.json
    else
        echo "[Data Collector] No Firebase credentials configured - Firestore sync disabled."
    fi
fi

# Launch the python application in unbuffered mode so logs appear instantly
exec python3 -u /app/main.py
