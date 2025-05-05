#!/usr/bin/with-contenv bashio

# Print banner
bashio::log.info "Starting Schnell Matter Controller"

# Activate virtual environment
source /opt/venv/bin/activate
bashio::log.info "Virtual environment activated"

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

# Run the debug script to help diagnose installation issues
bashio::log.info "Running debug script..."
if [ -x /usr/bin/debug-install.sh ]; then
    /usr/bin/debug-install.sh
else
    bashio::log.warning "Debug script not found or not executable"
    # Print some basic debug info
    bashio::log.info "Python version:"
    python --version
    bashio::log.info "Installed packages:"
    pip list | grep -E 'matter|fastapi|uvicorn'
fi

# Configure logging
mkdir -p /data/logs
touch /data/logs/matter_controller.log

# Create data directories if they don't exist
mkdir -p /data/matter_controller/credentials
mkdir -p /data/matter_server

# Set up Python path for Matter Server
export PYTHONPATH="${PYTHONPATH:-}:/opt/python-matter-server"

# Check if Matter Server module is available
if python -c "import matter_server" 2>/dev/null; then
    # Start the Matter Server in the background
    bashio::log.info "Starting Matter Server on port 5580..."

    # Try to start the Matter Server, but don't fail if it doesn't work
    {
        # Print Python path for debugging
        bashio::log.info "Python path: $PYTHONPATH"

        # Print installed packages for debugging
        bashio::log.info "Installed packages:"
        pip list | grep -E 'matter|chip'

        # Print GLIBC version for debugging
        bashio::log.info "GLIBC version:"
        ldd --version | head -n 1

        # Try to start the Matter Server with older version that's compatible with GLIBC
        cd /opt/python-matter-server
        python -m matter_server.server \
          --storage-path /data/matter_server \
          --log-level error \
          --listen-address 0.0.0.0 \
          --listen-port 5580 &
        MATTER_SERVER_PID=$!

        # Wait for Matter Server to start
        sleep 5

        # Check if the process is still running
        if kill -0 $MATTER_SERVER_PID 2>/dev/null; then
            bashio::log.info "Matter Server started successfully"
        else
            bashio::log.warning "Matter Server failed to start, using mock server instead"
            # Start mock server (will be defined in the else branch below)
            USE_MOCK_SERVER=true
        fi
    } || {
        bashio::log.warning "Error starting Matter Server, using mock server instead"
        USE_MOCK_SERVER=true
    }

    # If we need to use the mock server, set the flag
    if [ "${USE_MOCK_SERVER:-false}" = "true" ]; then
        # We'll fall through to the else branch
        false
    else
        # Matter Server started successfully
        true
    fi
else
    # If Matter Server is not available, create a mock server
    bashio::log.warning "Matter Server module not found, starting mock server..."

    # Create a simple mock server that listens on port 5580
    python -c "
import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('mock_matter_server')

async def handler(websocket):
    logger.info(f'Client connected: {websocket.remote_address}')
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                logger.info(f'Received: {data}')

                # Always return success
                response = {
                    'message_id': data.get('message_id', '0'),
                    'status': 'succeeded',
                    'result': {}
                }

                if data.get('command') == 'get_nodes':
                    response['result'] = {'nodes': []}

                await websocket.send(json.dumps(response))
            except Exception as e:
                logger.error(f'Error: {e}')
    except websockets.exceptions.ConnectionClosed:
        logger.info(f'Client disconnected: {websocket.remote_address}')

async def main():
    logger.info('Starting mock Matter Server on port 5580')
    async with websockets.serve(handler, '0.0.0.0', 5580):
        await asyncio.Future()  # Run forever

asyncio.run(main())
" &

    # Wait for mock server to start
    sleep 2
    bashio::log.info "Mock Matter Server started"
fi

# Create a simple mock API if needed
if [ ! -f /matter_controller/api.py ] || [ ! -f /matter_controller/controller.py ]; then
    bashio::log.warning "API files not found, creating mock API"
    mkdir -p /matter_controller

    # Create a simple API file
    cat > /matter_controller/api.py << 'EOF'
"""
Matter Controller API implementation.
"""
import os
import logging
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("matter_controller_api")

# Initialize FastAPI app
app = FastAPI(
    title="Schnell Matter Controller API",
    description="API for controlling Matter devices",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head>
            <title>Matter Controller API</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }
                h1 {
                    color: #2c3e50;
                }
            </style>
        </head>
        <body>
            <h1>Schnell Matter Controller API</h1>
            <p>This is a mock API for the Matter Controller.</p>
            <p>The actual implementation is not available.</p>
        </body>
    </html>
    """

@app.get("/api/devices")
async def get_devices():
    return {"devices": []}

@app.get("/api/hub")
async def get_hub_info():
    return {
        "version": "1.0.0",
        "status": "online",
        "device_count": 0
    }
EOF
fi

# Start the Matter Controller API
bashio::log.info "Starting Schnell Matter Controller API on port 8099..."
cd /matter_controller
python -m uvicorn api:app --host 0.0.0.0 --port 8099 --log-level $LOG_LEVEL || {
    bashio::log.error "Failed to start Matter Controller API"
    # Keep the container running for debugging
    tail -f /dev/null
}
