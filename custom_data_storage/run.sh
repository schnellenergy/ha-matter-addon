#!/bin/sh
set -e

echo "Starting Custom Data Storage Add-on..."

# Set default values
export LOG_LEVEL="${LOG_LEVEL:-info}"
export STORAGE_PATH="${STORAGE_PATH:-/data/custom_storage}"
export MAX_STORAGE_SIZE_MB="${MAX_STORAGE_SIZE_MB:-100}"
export ENABLE_WEBSOCKET="${ENABLE_WEBSOCKET:-true}"
export ENABLE_CORS="${ENABLE_CORS:-true}"
export API_KEY="${API_KEY:-}"

# Create storage directory if it doesn't exist
mkdir -p "${STORAGE_PATH}"
chmod 755 "${STORAGE_PATH}"

echo "Configuration:"
echo "  Log Level: ${LOG_LEVEL}"
echo "  Storage Path: ${STORAGE_PATH}"
echo "  Max Storage Size: ${MAX_STORAGE_SIZE_MB}MB"
echo "  WebSocket Enabled: ${ENABLE_WEBSOCKET}"
echo "  CORS Enabled: ${ENABLE_CORS}"
echo "  API Key Set: $([ -n "${API_KEY}" ] && echo "Yes" || echo "No")"

# Start the application
cd /app
echo "Starting SQLite storage application..."
exec python3 main_fixed.py
