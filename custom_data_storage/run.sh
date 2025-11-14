#!/usr/bin/with-contenv bashio

# Get configuration
LOG_LEVEL=$(bashio::config 'log_level')
STORAGE_PATH=$(bashio::config 'storage_path')
MAX_STORAGE_SIZE_MB=$(bashio::config 'max_storage_size_mb')
ENABLE_WEBSOCKET=$(bashio::config 'enable_websocket')
ENABLE_CORS=$(bashio::config 'enable_cors')
API_KEY=$(bashio::config 'api_key')

# Set environment variables
export LOG_LEVEL="${LOG_LEVEL}"
export STORAGE_PATH="${STORAGE_PATH}"
export MAX_STORAGE_SIZE_MB="${MAX_STORAGE_SIZE_MB}"
export ENABLE_WEBSOCKET="${ENABLE_WEBSOCKET}"
export ENABLE_CORS="${ENABLE_CORS}"
export API_KEY="${API_KEY}"

# Create storage directory if it doesn't exist
mkdir -p "${STORAGE_PATH}"

# Set permissions
chmod 755 "${STORAGE_PATH}"

bashio::log.info "Starting SQLite Custom Data Storage Add-on..."
bashio::log.info "Log Level: ${LOG_LEVEL}"
bashio::log.info "Storage Path: ${STORAGE_PATH}"
bashio::log.info "Storage Type: SQLite Database"
bashio::log.info "Max Storage Size: ${MAX_STORAGE_SIZE_MB}MB"
bashio::log.info "WebSocket Enabled: ${ENABLE_WEBSOCKET}"
bashio::log.info "CORS Enabled: ${ENABLE_CORS}"
bashio::log.info "API Key Set: $([ -n "${API_KEY}" ] && echo "Yes" || echo "No")"

# Start the SQLite application
cd /app
bashio::log.info "Using SQLite storage for professional data management"
exec python3 main_fixed.py
