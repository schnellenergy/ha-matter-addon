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

# Try to fetch IP from Firebase Firestore if service account exists
HA_IP_FROM_FIREBASE=""
if [ -f "/firebase-service-account.json" ]; then
    bashio::log.info "🔥 Firebase service account found - attempting to fetch HA IP from Firestore..."
    
    # Get MAC address of the hub
    MAC_ADDRESS=$(cat /sys/class/net/eth0/address 2>/dev/null | tr '[:lower:]' '[:upper:]' | tr -d ':')
    
    if [ -z "$MAC_ADDRESS" ]; then
        # Try wlan0 if eth0 doesn't exist
        MAC_ADDRESS=$(cat /sys/class/net/wlan0/address 2>/dev/null | tr '[:lower:]' '[:upper:]' | tr -d ':')
    fi
    
    if [ -n "$MAC_ADDRESS" ]; then
        # Format MAC address with colons (2C:CF:67:6E:11:52)
        MAC_WITH_COLONS=$(echo "$MAC_ADDRESS" | sed 's/../&:/g' | sed 's/:$//')
        bashio::log.info "📍 Hub MAC Address: $MAC_WITH_COLONS"
        
        # Fetch IP from Firebase using Python
        HA_IP_FROM_FIREBASE=$(python3 -c "
import sys
sys.path.insert(0, '/app')
from firestore_helper import FirestoreHelper

try:
    firestore = FirestoreHelper()
    ip = firestore.get_hub_ip('$MAC_WITH_COLONS')
    if ip:
        print(ip)
except Exception as e:
    print('', file=sys.stderr)
" 2>/dev/null)
        
        if [ -n "$HA_IP_FROM_FIREBASE" ]; then
            bashio::log.info "✅ Successfully fetched HA IP from Firebase: $HA_IP_FROM_FIREBASE"
        else
            bashio::log.warning "⚠️ Could not fetch IP from Firebase - will use fallback methods"
        fi
    else
        bashio::log.warning "⚠️ Could not determine MAC address - skipping Firebase IP fetch"
    fi
else
    bashio::log.info "ℹ️ No Firebase service account found - skipping Firestore IP fetch"
fi

# Determine Home Assistant hostname/IP
# Priority: 1) Firebase IP, 2) Manual IP (if set), 3) homeassistant.local (standard)
if [ -n "$HA_IP_FROM_FIREBASE" ]; then
    HA_HOST="$HA_IP_FROM_FIREBASE"
    bashio::log.info "🔥 Using IP from Firebase Firestore: ${HA_HOST}"
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
