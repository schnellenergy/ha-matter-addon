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
export COLLECT_HISTORICAL=$(bashio::config 'collect_historical')
export BATCH_SIZE=$(bashio::config 'batch_size')
export RETRY_ATTEMPTS=$(bashio::config 'retry_attempts')
export LOG_LEVEL=$(bashio::config 'log_level')
export EXCLUDED_DOMAINS=$(bashio::config 'excluded_domains' | jq -r '.[]' | tr '\n' ',' | sed 's/,$//')
export EXCLUDED_ENTITIES=$(bashio::config 'excluded_entities' | jq -r '.[]' | tr '\n' ',' | sed 's/,$//')
export INCLUDE_ATTRIBUTES=$(bashio::config 'include_attributes')

# Get Home Assistant URL from Supervisor
# This allows the addon to automatically connect to the HA instance it's running on
export HA_URL="http://supervisor/core"
export HA_WEBSOCKET_URL="ws://supervisor/core/websocket"

bashio::log.info "Configuration loaded successfully"
bashio::log.info "Google Sheets URL: ${GOOGLE_SHEETS_URL}"
bashio::log.info "Collect Historical: ${COLLECT_HISTORICAL}"
bashio::log.info "Batch Size: ${BATCH_SIZE}"
bashio::log.info "Log Level: ${LOG_LEVEL}"
bashio::log.info "Home Assistant URL: ${HA_URL}"

# Start the Python application
cd /app
python3 main.py
