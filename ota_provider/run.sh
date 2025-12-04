#!/usr/bin/with-contenv bashio

# Get configuration
DISCRIMINATOR=$(bashio::config 'discriminator')
PASSCODE=$(bashio::config 'passcode')
PORT=$(bashio::config 'port')
OTA_FILES_PATH=$(bashio::config 'ota_files_path')

bashio::log.info "Starting Matter OTA Provider..."
bashio::log.info "Discriminator: ${DISCRIMINATOR}"
bashio::log.info "Port: ${PORT}"
bashio::log.info "OTA Files Path: ${OTA_FILES_PATH}"

# Ensure OTA files directory exists
mkdir -p "${OTA_FILES_PATH}"

# Start the OTA provider
exec /usr/local/bin/chip-ota-provider-app \
    --filepath "${OTA_FILES_PATH}" \
    --discriminator "${DISCRIMINATOR}" \
    --passcode "${PASSCODE}" \
    --secured-device-port "${PORT}"

