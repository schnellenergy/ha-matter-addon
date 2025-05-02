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

# Create a simple HTTP server for testing
cat > /tmp/server.py << 'EOF'
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Matter Controller API is running"}

@app.get("/api/devices")
async def get_devices():
    return {"devices": []}

@app.post("/api/commission")
async def commission_device(setup_code: str = None, device_name: str = None):
    return {"success": True, "device_id": "mock-device-123", "name": device_name or "Mock Device"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8099)
EOF

# Start the Matter Controller API
bashio::log.info "Starting Matter Controller API on port 8099..."
python3 /tmp/server.py
