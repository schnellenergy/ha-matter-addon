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
export HA_IP_MANUAL=$(bashio::config 'ha_ip')
export HA_PORT=$(bashio::config 'ha_port')
export COLLECT_HISTORICAL=$(bashio::config 'collect_historical')
export BATCH_SIZE=$(bashio::config 'batch_size')
export RETRY_ATTEMPTS=$(bashio::config 'retry_attempts')
export LOG_LEVEL=$(bashio::config 'log_level')
export EXCLUDED_DOMAINS=$(bashio::config 'excluded_domains' | jq -r '.[]' | tr '\n' ',' | sed 's/,$//')
export EXCLUDED_ENTITIES=$(bashio::config 'excluded_entities' | jq -r '.[]' | tr '\n' ',' | sed 's/,$//')
export INCLUDE_ATTRIBUTES=$(bashio::config 'include_attributes')

# Try to fetch IP from Custom Data Storage addon
HA_IP_FROM_STORAGE=""
STORAGE_ADDON_URL="http://172.30.32.1:8100"  # Custom Data Storage addon internal URL

bashio::log.info "📦 Attempting to fetch HA IP from Custom Data Storage addon..."

# Fetch hub_ip from Custom Data Storage addon
STORAGE_RESPONSE=$(curl -s -m 5 "${STORAGE_ADDON_URL}/api/data/home_setup" 2>/dev/null || echo "")

if [ -n "$STORAGE_RESPONSE" ]; then
    # Extract hub_ip from JSON response: data.structure.hub_ip
    HUB_IP_WITH_PORT=$(echo "$STORAGE_RESPONSE" | jq -r '.data.structure.hub_ip // empty' 2>/dev/null || echo "")
    
    if [ -n "$HUB_IP_WITH_PORT" ] && [ "$HUB_IP_WITH_PORT" != "null" ]; then
        # Extract just the IP from "http://192.168.x.x:8123"
        HA_IP_FROM_STORAGE=$(echo "$HUB_IP_WITH_PORT" | sed -E 's|https?://([^:]+):.*|\1|')
        
        if [ -n "$HA_IP_FROM_STORAGE" ]; then
            bashio::log.info "✅ Successfully fetched HA IP from Custom Data Storage: $HA_IP_FROM_STORAGE"
        else
            bashio::log.warning "⚠️ Could not parse IP from Custom Data Storage response"
        fi
    else
        bashio::log.warning "⚠️ No hub_ip found in Custom Data Storage response"
    fi
else
    bashio::log.warning "⚠️ Could not connect to Custom Data Storage addon"
fi

# Determine Home Assistant hostname/IP
# Priority: 1) Custom Data Storage IP, 2) Manual IP (if set), 3) homeassistant.local (standard)
if [ -n "$HA_IP_FROM_STORAGE" ]; then
    HA_HOST="$HA_IP_FROM_STORAGE"
    bashio::log.info "📦 Using IP from Custom Data Storage addon: ${HA_HOST}"
elif [ -n "$HA_IP_MANUAL" ] && [ "$HA_IP_MANUAL" != "null" ] && [ "$HA_IP_MANUAL" != "" ]; then
    HA_HOST="$HA_IP_MANUAL"
    bashio::log.info "Using manually configured IP: ${HA_HOST}"
else
    # Use homeassistant.local - this is the standard hostname that works even when IP changes
    HA_HOST="homeassistant.local"
    bashio::log.info "Using standard hostname: ${HA_HOST}"
fi

# Construct Home Assistant URL with hostname and configured port
export HA_URL="http://${HA_HOST}:${HA_PORT}"
export HA_WEBSOCKET_URL="ws://${HA_HOST}:${HA_PORT}/api/websocket"

bashio::log.info "Configuration loaded successfully"
bashio::log.info "Google Sheets URL: ${GOOGLE_SHEETS_URL}"
bashio::log.info "Collect Historical: ${COLLECT_HISTORICAL}"
bashio::log.info "Batch Size: ${BATCH_SIZE}"
bashio::log.info "Log Level: ${LOG_LEVEL}"
bashio::log.info "Home Assistant Host: ${HA_HOST}"
bashio::log.info "Home Assistant Port: ${HA_PORT}"
bashio::log.info "Home Assistant URL: ${HA_URL}"

# Start the Python application
cd /app
python3 main.py
