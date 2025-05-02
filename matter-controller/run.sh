#!/usr/bin/with-contenv bashio

# Get config
LOG_LEVEL=$(bashio::config 'log_level')

# Create data directory
mkdir -p /data/matter_server

# Start the Matter Server
bashio::log.info "Starting Matter Server..."
python3 -m matter_server.server \
  --storage-path /data/matter_server \
  --log-level error \
  --listen-address 0.0.0.0 \
  --listen-port 5580
