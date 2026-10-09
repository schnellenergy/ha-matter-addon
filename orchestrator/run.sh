#!/usr/bin/env bash
set -e

echo "[Schnell Orchestrator] Starting Hub Watchdog and Lifecycle Manager..."

# Extract potential Google Cloud credentials if provided as options
# (Assuming the user might mount them later, for now we just run the app)

# Launch the python application in unbuffered mode so logs appear instantly
exec python3 -u /app/main.py
