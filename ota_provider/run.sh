#!/bin/bash
set -e

# Read configuration from options.json (Home Assistant add-on config)
CONFIG_PATH="/data/options.json"

# Default values
DISCRIMINATOR=3840
PASSCODE=20202021
PORT=5580
OTA_FILES_PATH="/share/ota-files"

# Read from config if available
if [ -f "$CONFIG_PATH" ]; then
    DISCRIMINATOR=$(jq -r '.discriminator // 3840' "$CONFIG_PATH")
    PASSCODE=$(jq -r '.passcode // 20202021' "$CONFIG_PATH")
    PORT=$(jq -r '.port // 5580' "$CONFIG_PATH")
    OTA_FILES_PATH=$(jq -r '.ota_files_path // "/share/ota-files"' "$CONFIG_PATH")
fi

echo "Starting Matter OTA Provider..."
echo "Discriminator: ${DISCRIMINATOR}"
echo "Port: ${PORT}"
echo "OTA Files Path: ${OTA_FILES_PATH}"

# Ensure OTA files directory exists
mkdir -p "${OTA_FILES_PATH}"

# Start the OTA provider
exec /usr/local/bin/chip-ota-provider-app \
    --filepath "${OTA_FILES_PATH}" \
    --discriminator "${DISCRIMINATOR}" \
    --passcode "${PASSCODE}" \
    --secured-device-port "${PORT}"

