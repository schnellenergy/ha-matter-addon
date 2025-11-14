#!/usr/bin/env bash
set -e

# Parse configuration
CONFIG_PATH="/data/options.json"
LOG_LEVEL=$(jq --raw-output '.log_level // "info"' $CONFIG_PATH)
HA_TOKEN=$(jq --raw-output '.ha_token // ""' $CONFIG_PATH)
AUTO_BACKUP=$(jq --raw-output '.auto_backup // true' $CONFIG_PATH)
BACKUP_INTERVAL=$(jq --raw-output '.backup_interval_hours // 24' $CONFIG_PATH)

# Export environment variables
export LOG_LEVEL="$LOG_LEVEL"
export HA_TOKEN="$HA_TOKEN"
export AUTO_BACKUP="$AUTO_BACKUP"
export BACKUP_INTERVAL_HOURS="$BACKUP_INTERVAL"

# Create necessary directories
mkdir -p /data/db
mkdir -p /data/backups
mkdir -p /data/logs

# Set permissions
chmod 755 /data/db
chmod 755 /data/backups
chmod 755 /data/logs

echo "Starting Schnell Storage Add-on..."
echo "Log Level: $LOG_LEVEL"
echo "Auto Backup: $AUTO_BACKUP"
echo "Backup Interval: $BACKUP_INTERVAL hours"

# Start the FastAPI application
cd /app
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8080 \
    --log-level "$LOG_LEVEL" \
    --access-log \
    --reload
