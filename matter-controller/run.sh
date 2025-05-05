#!/usr/bin/with-contenv bashio

# Print banner
bashio::log.info "Starting Schnell Matter Controller"

# Get configuration
LOG_LEVEL=$(bashio::config 'log_level')

# Run the debug script to help diagnose installation issues
bashio::log.info "Running debug script..."
if [ -x /usr/bin/debug-install.sh ]; then
    /usr/bin/debug-install.sh
else
    bashio::log.warning "Debug script not found or not executable"
    # Print some basic debug info
    bashio::log.info "Python version:"
    python3 --version
    bashio::log.info "Installed packages:"
    pip3 list | grep -E 'fastapi|uvicorn'
fi

# Configure logging
mkdir -p /data/logs
touch /data/logs/matter_controller.log

# Create data directories if they don't exist
mkdir -p /data/matter_controller/credentials
mkdir -p /data/matter_server

# Start a mock Matter Server
bashio::log.info "Starting mock Matter Server on port 5580..."

# Create a simple mock server that listens on port 5580
python3 -c "
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

# Start the Matter Controller API
bashio::log.info "Starting Schnell Matter Controller API on port 8099..."
cd /matter_controller
python3 -m uvicorn api:app --host 0.0.0.0 --port 8099 --log-level $LOG_LEVEL || {
    bashio::log.error "Failed to start Matter Controller API"
    # Keep the container running for debugging
    tail -f /dev/null
}
