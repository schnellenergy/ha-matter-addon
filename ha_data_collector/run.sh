#!/usr/bin/with-contenv bashio

# ==============================================================================
# Home Assistant Data Collector Add-on
# Collects HA events and sends to Google Sheets
# ==============================================================================

bashio::log.info "Starting Home Assistant Data Collector..."

# Check if required configuration is provided
if ! bashio::config.has_value 'ha_token'; then
    bashio::log.fatal "Home Assistant token is required!"
    bashio::exit.nok
fi

if ! bashio::config.has_value 'google_sheets_url'; then
    bashio::log.fatal "Google Sheets URL is required!"
    bashio::exit.nok
fi

# Export configuration as environment variables
export HA_TOKEN=$(bashio::config 'ha_token')
export GOOGLE_SHEETS_URL=$(bashio::config 'google_sheets_url')
export HA_PORT=$(bashio::config 'ha_port')
export COLLECT_HISTORICAL=$(bashio::config 'collect_historical')
export BATCH_SIZE=$(bashio::config 'batch_size')
export RETRY_ATTEMPTS=$(bashio::config 'retry_attempts')
export LOG_LEVEL=$(bashio::config 'log_level')
export EXCLUDED_DOMAINS=$(bashio::config 'excluded_domains' | jq -r '.[]' | tr '\n' ',' | sed 's/,$//')
export EXCLUDED_ENTITIES=$(bashio::config 'excluded_entities' | jq -r '.[]' | tr '\n' ',' | sed 's/,$//')
export INCLUDE_ATTRIBUTES=$(bashio::config 'include_attributes')

# Auto-detect Home Assistant IP address
# Try multiple methods to get the HA IP
HA_IP=""

# Method 1: Try to get from supervisor API
if command -v bashio::api.supervisor \u003e/dev/null 2\u003e\u00261; then
    HA_IP=$(bashio::api.supervisor GET /core/info | jq -r '.data.ip_address // empty' 2\u003e/dev/null || echo "")
fi

# Method 2: If that fails, try to get from network info
if [ -z "$HA_IP" ]; then
    HA_IP=$(bashio::network.ipv4_address 2\u003e/dev/null | awk '{print $1}' || echo "")
fi

# Method 3: If still empty, try hostname resolution
if [ -z "$HA_IP" ]; then
    HA_IP=$(getent hosts homeassistant.local | awk '{print $1}' || echo "")
fi

# Method 4: Last resort - use gateway IP (usually the HA server)
if [ -z "$HA_IP" ]; then
    HA_IP=$(ip route | grep default | awk '{print $3}' || echo "192.168.1.1")
fi

# Construct Home Assistant URL with auto-detected IP and configured port
export HA_URL="http://${HA_IP}:${HA_PORT}"
export HA_WEBSOCKET_URL="ws://${HA_IP}:${HA_PORT}/api/websocket"

bashio::log.info "Configuration loaded successfully"
bashio::log.info "Google Sheets URL: ${GOOGLE_SHEETS_URL}"
bashio::log.info "Collect Historical: ${COLLECT_HISTORICAL}"
bashio::log.info "Batch Size: ${BATCH_SIZE}"
bashio::log.info "Log Level: ${LOG_LEVEL}"
bashio::log.info "Detected Home Assistant IP: ${HA_IP}"
bashio::log.info "Home Assistant Port: ${HA_PORT}"
bashio::log.info "Home Assistant URL: ${HA_URL}"

# Start the Python application
cd /app
python3 main.py
