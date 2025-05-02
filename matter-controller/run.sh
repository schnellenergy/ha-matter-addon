#!/usr/bin/with-contenv bashio

# Get config
LOG_LEVEL=$(bashio::config 'log_level')

# Create data directory
mkdir -p /data/matter_server

# Print some debug info
bashio::log.info "Python version:"
python3 --version
bashio::log.info "Installed packages:"
pip3 list

# Start the Matter Server
bashio::log.info "Starting Matter Server..."
python3 -m matter_server.server \
  --storage-path /data/matter_server \
  --log-level error \
  --listen-address 0.0.0.0 \
  --listen-port 5580
