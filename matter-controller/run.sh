#!/usr/bin/with-contenv bashio

# Print banner
bashio::log.info "Starting Schnell Matter Controller"

# Get configuration
LOG_LEVEL=$(bashio::config 'log_level')
TOKEN_LIFETIME_DAYS=$(bashio::config 'token_lifetime_days' '30')
ALLOW_EXTERNAL_COMMISSIONING=$(bashio::config 'allow_external_commissioning' 'true')
ANALYTICS_ENABLED=$(bashio::config 'analytics_enabled' 'true')
MAX_LOG_ENTRIES=$(bashio::config 'max_log_entries' '1000')
MAX_ANALYTICS_EVENTS=$(bashio::config 'max_analytics_events' '1000')
AUTO_REGISTER_WITH_HA=$(bashio::config 'auto_register_with_ha' 'true')

# Export configuration as environment variables
export LOG_LEVEL
export TOKEN_LIFETIME_DAYS
export ALLOW_EXTERNAL_COMMISSIONING
export ANALYTICS_ENABLED
export MAX_LOG_ENTRIES
export MAX_ANALYTICS_EVENTS
export AUTO_REGISTER_WITH_HA
export STARTUP_TIME=$(date +%s)

# Run the debug script to help diagnose installation issues
bashio::log.info "Running debug script..."
/usr/bin/debug-install.sh

# Configure logging
mkdir -p /data/logs
touch /data/logs/matter_controller.log

# Create data directories if they don't exist
mkdir -p /data/matter_controller/credentials
mkdir -p /data/matter_server

# Set up Python path for Matter Server
export PYTHONPATH="${PYTHONPATH}:/opt/python-matter-server"

# Start the Matter Server in the background
bashio::log.info "Starting Matter Server on port 5580..."
python3 -m matter_server.server \
  --storage-path /data/matter_server \
  --log-level error \
  --listen-address 0.0.0.0 \
  --listen-port 5580 &

# Wait for Matter Server to start
sleep 5
bashio::log.info "Matter Server started"

# Start the Matter Controller API
bashio::log.info "Starting Schnell Matter Controller API on port 8099..."
cd /matter_controller
python3 -m uvicorn api:app --host 0.0.0.0 --port 8099 --log-level $LOG_LEVEL
