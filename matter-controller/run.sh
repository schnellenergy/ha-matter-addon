#!/usr/bin/with-contenv bashio

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

# Create a mock Matter Server WebSocket service
bashio::log.info "Creating mock Matter Server WebSocket service..."
cat > /tmp/mock_matter_server.py << 'EOF'
import asyncio
import json
import logging
import uuid
import time
import websockets
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mock_matter_server")

# Mock devices
DEVICES = [
    {
        "node_id": "device-001",
        "name": "Living Room Light",
        "vendor_id": 4660,
        "product_id": 22136,
        "commissioned_at": int(time.time()) - 3600,
        "status": "online",
        "device_type": "light"
    },
    {
        "node_id": "device-002",
        "name": "Kitchen Switch",
        "vendor_id": 4660,
        "product_id": 22137,
        "commissioned_at": int(time.time()) - 7200,
        "status": "online",
        "device_type": "switch"
    }
]

# Save devices to file
with open("/data/matter_server/devices.json", "w") as f:
    json.dump({"nodes": DEVICES}, f)

# WebSocket handler
async def handle_websocket(websocket, path):
    logger.info(f"Client connected: {websocket.remote_address}")

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                message_id = data.get("message_id", str(uuid.uuid4()))
                command = data.get("command", "")
                args = data.get("args", {})

                logger.info(f"Received command: {command}, args: {args}")

                # Handle different commands
                if command == "get_nodes":
                    response = {
                        "message_id": message_id,
                        "status": "succeeded",
                        "result": {"nodes": DEVICES}
                    }
                elif command == "commission_with_code":
                    # Create a new device
                    setup_code = args.get("code", "")
                    new_device_id = f"device-{str(uuid.uuid4())[:8]}"

                    new_device = {
                        "node_id": new_device_id,
                        "name": f"New Device {new_device_id}",
                        "vendor_id": 4660,
                        "product_id": 22136,
                        "commissioned_at": int(time.time()),
                        "status": "online",
                        "device_type": "light" if "light" in setup_code.lower() else "switch"
                    }

                    DEVICES.append(new_device)

                    # Save updated devices to file
                    with open("/data/matter_server/devices.json", "w") as f:
                        json.dump({"nodes": DEVICES}, f)

                    response = {
                        "message_id": message_id,
                        "status": "succeeded",
                        "result": {"node_id": new_device_id}
                    }
                elif command == "device_info":
                    node_id = args.get("node_id", "")
                    device = next((d for d in DEVICES if d["node_id"] == node_id), None)

                    if device:
                        response = {
                            "message_id": message_id,
                            "status": "succeeded",
                            "result": device
                        }
                    else:
                        response = {
                            "message_id": message_id,
                            "status": "failed",
                            "error": {"message": f"Device not found: {node_id}"}
                        }
                elif command == "remove_node":
                    node_id = args.get("node_id", "")
                    device_index = next((i for i, d in enumerate(DEVICES) if d["node_id"] == node_id), None)

                    if device_index is not None:
                        DEVICES.pop(device_index)

                        # Save updated devices to file
                        with open("/data/matter_server/devices.json", "w") as f:
                            json.dump({"nodes": DEVICES}, f)

                        response = {
                            "message_id": message_id,
                            "status": "succeeded",
                            "result": {}
                        }
                    else:
                        response = {
                            "message_id": message_id,
                            "status": "failed",
                            "error": {"message": f"Device not found: {node_id}"}
                        }
                elif command == "create_binding":
                    # Just return success for any binding request
                    response = {
                        "message_id": message_id,
                        "status": "succeeded",
                        "result": {}
                    }
                elif command == "trigger_ota_update":
                    # Just return success for any OTA update request
                    response = {
                        "message_id": message_id,
                        "status": "succeeded",
                        "result": {}
                    }
                elif command == "server_info":
                    response = {
                        "message_id": message_id,
                        "status": "succeeded",
                        "result": {
                            "fabric_id": "mock-fabric-123",
                            "version": "1.0.0",
                            "uptime": int(time.time()) - int(time.time()) + 3600
                        }
                    }
                else:
                    response = {
                        "message_id": message_id,
                        "status": "failed",
                        "error": {"message": f"Unknown command: {command}"}
                    }

                await websocket.send(json.dumps(response))

            except json.JSONDecodeError:
                logger.error(f"Invalid JSON: {message}")
                await websocket.send(json.dumps({
                    "status": "failed",
                    "error": {"message": "Invalid JSON"}
                }))

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Client disconnected: {websocket.remote_address}")

# Start WebSocket server
async def main():
    logger.info("Starting mock Matter Server WebSocket on port 5580...")
    async with websockets.serve(handle_websocket, "0.0.0.0", 5580):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
EOF

# Start the mock Matter Server in the background
bashio::log.info "Starting mock Matter Server on port 5580..."
python3 /tmp/mock_matter_server.py &

# Wait for the mock Matter Server to start
sleep 2

# Start the Matter Controller API
bashio::log.info "Starting Schnell Matter Controller API on port 8099..."
cd /matter_controller
python3 -m uvicorn api:app --host 0.0.0.0 --port 8099 --log-level $LOG_LEVEL
