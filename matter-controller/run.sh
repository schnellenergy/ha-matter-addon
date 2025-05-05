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

# Check if port 5580 is already in use
if netstat -tuln | grep -q ":5580 "; then
    bashio::log.info "Port 5580 is already in use, assuming Matter Server is already running"
else
    # Start a mock Matter Server
    bashio::log.info "Starting mock Matter Server on port 5580..."

    # Create a simple mock server that listens on port 5580
    python3 -c "
import asyncio
import websockets
import json
import logging
import socket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('mock_matter_server')

# Check if port is in use
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

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
    # Check if port is already in use
    if is_port_in_use(5580):
        logger.warning('Port 5580 is already in use, cannot start mock server')
        return

    logger.info('Starting mock Matter Server on port 5580')
    try:
        async with websockets.serve(handler, '0.0.0.0', 5580):
            await asyncio.Future()  # Run forever
    except OSError as e:
        logger.error(f'Failed to start server: {e}')

asyncio.run(main())
" &

    # Wait for mock server to start
    sleep 2
    bashio::log.info "Mock Matter Server started"
fi

# Start the Matter Controller API
bashio::log.info "Starting Schnell Matter Controller API on port 8099..."
cd /matter_controller

# Create a simple API file if it doesn't exist or has issues
cat > /matter_controller/simple_api.py << 'EOF'
"""
Simple Matter Controller API implementation.
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

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

# JWT secret key (generate a new one each time the add-on starts)
SECRET_KEY = str(uuid.uuid4())
ALGORITHM = "HS256"

# Token lifetime
TOKEN_LIFETIME_DAYS = 30

# OAuth2 scheme (optional for some endpoints)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/token", auto_error=False)

# Models
class TokenRequest(BaseModel):
    client_id: str
    client_name: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: int

# Helper function to get current user (optional)
async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)):
    if token is None:
        return None
    try:
        # In a real implementation, we would decode the JWT token here
        return {"client_id": "anonymous"}
    except Exception:
        return None

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
                h2 {
                    color: #3498db;
                    margin-top: 30px;
                }
                pre {
                    background-color: #f8f9fa;
                    padding: 10px;
                    border-radius: 5px;
                    overflow-x: auto;
                }
                code {
                    font-family: monospace;
                }
                .endpoint {
                    margin-bottom: 20px;
                    padding: 10px;
                    border-left: 4px solid #3498db;
                    background-color: #f8f9fa;
                }
                .method {
                    font-weight: bold;
                    color: #e74c3c;
                }
            </style>
        </head>
        <body>
            <h1>Schnell Matter Controller API</h1>
            <p>This is a simple API for the Matter Controller.</p>

            <h2>Authentication</h2>
            <div class="endpoint">
                <p><span class="method">POST</span> /api/token</p>
                <p>Get an API token for authentication</p>
                <pre><code>{
  "client_id": "your_client_id",
  "client_name": "Your Client Name"
}</code></pre>
            </div>

            <h2>Device Management</h2>
            <div class="endpoint">
                <p><span class="method">GET</span> /api/devices</p>
                <p>List all commissioned devices</p>
            </div>

            <div class="endpoint">
                <p><span class="method">GET</span> /api/hub</p>
                <p>Get information about the Matter hub</p>
            </div>
        </body>
    </html>
    """

@app.post("/api/token", response_model=TokenResponse)
async def create_token(request: TokenRequest):
    # Create a new token
    expires_at = datetime.now() + timedelta(days=TOKEN_LIFETIME_DAYS)

    # In a real implementation, we would encode a JWT token here
    access_token = f"dummy_token_{request.client_id}"

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_at": int(expires_at.timestamp())
    }

@app.get("/api/devices")
async def get_devices(user: Dict = Depends(get_current_user)):
    # This endpoint works with or without authentication
    return {"devices": []}

@app.get("/api/hub")
async def get_hub_info(user: Dict = Depends(get_current_user)):
    # This endpoint works with or without authentication
    return {
        "version": "1.0.0",
        "status": "online",
        "device_count": 0
    }
EOF

# Try to start the main API first, if it fails, use the simple API
python3 -m uvicorn api:app --host 0.0.0.0 --port 8099 --log-level $LOG_LEVEL || {
    bashio::log.warning "Failed to start main API, using simple API instead"
    python3 -m uvicorn simple_api:app --host 0.0.0.0 --port 8099 --log-level $LOG_LEVEL || {
        bashio::log.error "Failed to start Matter Controller API"
        # Keep the container running for debugging
        tail -f /dev/null
    }
}
