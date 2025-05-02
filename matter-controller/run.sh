#!/usr/bin/with-contenv bashio

# Get configuration
LOG_LEVEL=$(bashio::config 'log_level')
LOG_LEVEL_SDK=$(bashio::config 'log_level_sdk')
TOKEN_LIFETIME_DAYS=$(bashio::config 'token_lifetime_days')
ALLOW_EXTERNAL_COMMISSIONING=$(bashio::config 'allow_external_commissioning')

# Export configuration as environment variables
export LOG_LEVEL
export LOG_LEVEL_SDK
export TOKEN_LIFETIME_DAYS
export ALLOW_EXTERNAL_COMMISSIONING
export STARTUP_TIME=$(date +%s)

# Configure logging
mkdir -p /data/logs
touch /data/logs/matter_controller.log

# Create data directories if they don't exist
mkdir -p /data/matter_controller/credentials
mkdir -p /data/matter_server

# Print some debug info
bashio::log.info "Python version:"
python3 --version
bashio::log.info "Installed packages:"
pip3 list

# Start the Matter Controller API
bashio::log.info "Starting Matter Controller API on port 8099..."
cd /matter_controller
python3 -m uvicorn api:app --host 0.0.0.0 --port 8099 --log-level $LOG_LEVEL
