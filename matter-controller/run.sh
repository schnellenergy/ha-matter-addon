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
from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel
import uvicorn
import time
import uuid
from typing import Optional, Dict, Any, List

# Models for request/response
class TokenRequest(BaseModel):
    client_id: str
    client_name: str

class CommissionRequest(BaseModel):
    setup_code: str
    device_name: Optional[str] = None

# Sample devices for testing
SAMPLE_DEVICES = [
    {
        "id": "device-001",
        "name": "Living Room Light",
        "vendor_id": 4660,
        "product_id": 22136,
        "commissioned_at": int(time.time()) - 3600,
        "status": "online",
        "type": "light"
    },
    {
        "id": "device-002",
        "name": "Kitchen Switch",
        "vendor_id": 4660,
        "product_id": 22137,
        "commissioned_at": int(time.time()) - 7200,
        "status": "online",
        "type": "switch"
    }
]

# In-memory token storage
TOKENS = {}

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Matter Controller API is running"}

@app.post("/api/token")
async def create_token(request: TokenRequest):
    # Create a simple token
    token = f"token_{uuid.uuid4()}"
    expires_in = 86400 * 30  # 30 days in seconds

    # Store token info
    TOKENS[token] = {
        "client_id": request.client_id,
        "client_name": request.client_name,
        "created_at": int(time.time())
    }

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in
    }

@app.get("/api/devices")
async def get_devices():
    return {"devices": SAMPLE_DEVICES}

@app.post("/api/commission")
async def commission_device(request: CommissionRequest):
    # Create a new device
    device_id = f"device-{uuid.uuid4()}"
    new_device = {
        "id": device_id,
        "name": request.device_name or f"New Device {device_id[:8]}",
        "vendor_id": 4660,
        "product_id": 22136,
        "commissioned_at": int(time.time()),
        "status": "online",
        "type": "light" if "light" in request.setup_code.lower() else "switch"
    }

    # Add to sample devices
    SAMPLE_DEVICES.append(new_device)

    return {
        "success": True,
        "device_id": device_id,
        "name": new_device["name"],
        "device": new_device
    }

@app.delete("/api/devices/{device_id}")
async def remove_device(device_id: str):
    # Find and remove the device
    for i, device in enumerate(SAMPLE_DEVICES):
        if device["id"] == device_id:
            SAMPLE_DEVICES.pop(i)
            return {"success": True}

    raise HTTPException(status_code=404, detail="Device not found")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8099)
EOF

# Start the Matter Controller API
bashio::log.info "Starting Matter Controller API on port 8099..."
python3 /tmp/server.py
