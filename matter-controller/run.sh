#!/usr/bin/with-contenv bashio

# Get config
LOG_LEVEL=$(bashio::config 'log_level')

# Create data directory
mkdir -p /data/matter_controller

# Print some debug info
bashio::log.info "Python version:"
python3 --version
bashio::log.info "Installed packages:"
pip3 list

# Create a simple API server
cat > /tmp/api.py << 'EOF'
from fastapi import FastAPI
import uvicorn
import os
import json

app = FastAPI(title="Matter Controller API")

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

# Start the API server
bashio::log.info "Starting Matter Controller API on port 8099..."
python3 /tmp/api.py
