#!/bin/sh
set -e

echo "Starting Custom Data Storage Add-on..."

# HA supervisor writes addon options to /data/options.json.
# Parse it here so env vars are available to the Python process
# even if something reads them before main_fixed.py does.
if [ -f /data/options.json ]; then
    export LOG_LEVEL="$(python3 -c "import json,sys; print(json.load(open('/data/options.json')).get('log_level','info'))")"
    export STORAGE_PATH="$(python3 -c "import json,sys; print(json.load(open('/data/options.json')).get('storage_path','/data/custom_storage'))")"
    export MAX_STORAGE_SIZE_MB="$(python3 -c "import json,sys; print(json.load(open('/data/options.json')).get('max_storage_size_mb',2000))")"
    export ENABLE_WEBSOCKET="$(python3 -c "import json,sys; print(str(json.load(open('/data/options.json')).get('enable_websocket',True)).lower())")"
    export ENABLE_CORS="$(python3 -c "import json,sys; print(str(json.load(open('/data/options.json')).get('enable_cors',True)).lower())")"
    export API_KEY="$(python3 -c "import json,sys; print(json.load(open('/data/options.json')).get('api_key',''))")"
    export SECURE_HA_TOKEN="$(python3 -c "import json,sys; print(json.load(open('/data/options.json')).get('secure_ha_token',''))")"
else
    # Fallback defaults (options.json absent in local dev / testing)
    export LOG_LEVEL="${LOG_LEVEL:-info}"
    export STORAGE_PATH="${STORAGE_PATH:-/data/custom_storage}"
    export MAX_STORAGE_SIZE_MB="${MAX_STORAGE_SIZE_MB:-2000}"
    export ENABLE_WEBSOCKET="${ENABLE_WEBSOCKET:-true}"
    export ENABLE_CORS="${ENABLE_CORS:-true}"
    export API_KEY="${API_KEY:-}"
    export SECURE_HA_TOKEN="${SECURE_HA_TOKEN:-}"
fi

# Create storage directory if it doesn't exist
mkdir -p "${STORAGE_PATH}"
chmod 755 "${STORAGE_PATH}"

echo "Configuration:"
echo "  Log Level: ${LOG_LEVEL}"
echo "  Storage Path: ${STORAGE_PATH}"
echo "  Max Storage Size: ${MAX_STORAGE_SIZE_MB}MB"
echo "  WebSocket Enabled: ${ENABLE_WEBSOCKET}"
echo "  CORS Enabled: ${ENABLE_CORS}"
echo "  API Key Set: $([ -n "${API_KEY}" ] && echo 'Yes' || echo 'No')"
echo "  HA Token Set: $([ -n "${SECURE_HA_TOKEN}" ] && echo 'Yes' || echo 'No')"

# Start the application
cd /app
echo "Starting SQLite storage application..."
exec python3 main_fixed.py
