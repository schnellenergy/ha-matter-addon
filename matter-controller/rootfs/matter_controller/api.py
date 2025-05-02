"""
Matter Controller API implementation.
"""
import os
import logging
import time
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import jwt

from .controller import MatterController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/data/logs/matter_controller.log"),
        logging.StreamHandler()
    ]
)
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

# Initialize Matter controller
controller = MatterController()

# JWT secret key
SECRET_KEY = str(uuid.uuid4())
ALGORITHM = "HS256"

# Token lifetime
TOKEN_LIFETIME_DAYS = int(os.environ.get("TOKEN_LIFETIME_DAYS", 30))

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# WebSocket connections
ws_connections = {
    "devices": [],
    "logs": [],
    "analytics": []
}

# Models
class TokenRequest(BaseModel):
    client_id: str
    client_name: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: int

class CommissionRequest(BaseModel):
    setup_code: str
    device_name: Optional[str] = None

class BindingRequest(BaseModel):
    source_device_id: str
    target_device_id: str
    cluster_id: int

class OTAUpdateRequest(BaseModel):
    device_id: str

class AnalyticsRequest(BaseModel):
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    event_types: Optional[List[str]] = None

class LogsRequest(BaseModel):
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    log_types: Optional[List[str]] = None
    limit: Optional[int] = 100

# Helper functions
async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        client_id = payload.get("sub")
        if client_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return {"client_id": client_id}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

async def broadcast_to_websockets(channel: str, data: Dict[str, Any]):
    """Broadcast data to all connected WebSockets for a channel."""
    for ws in ws_connections.get(channel, []):
        try:
            await ws.send_json(data)
        except Exception as e:
            logger.error(f"Failed to send WebSocket message: {e}")

# Routes
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
            <p>This API allows you to interact with Matter devices through the Schnell Matter Controller add-on.</p>

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
                <p><span class="method">POST</span> /api/commission</p>
                <p>Commission a device using a setup code</p>
                <pre><code>{
  "setup_code": "MT:ABCDEFG",
  "device_name": "Living Room Light"
}</code></pre>
            </div>

            <div class="endpoint">
                <p><span class="method">GET</span> /api/devices</p>
                <p>List all commissioned devices</p>
            </div>

            <div class="endpoint">
                <p><span class="method">DELETE</span> /api/devices/{id}</p>
                <p>Remove a device</p>
            </div>

            <h2>Device Control</h2>
            <div class="endpoint">
                <p><span class="method">POST</span> /api/binding</p>
                <p>Create a binding between devices</p>
                <pre><code>{
  "source_device_id": "123456",
  "target_device_id": "789012",
  "cluster_id": 6
}</code></pre>
            </div>

            <div class="endpoint">
                <p><span class="method">POST</span> /api/ota/update</p>
                <p>Trigger an OTA update for a device</p>
                <pre><code>{
  "device_id": "123456"
}</code></pre>
            </div>

            <h2>Analytics and Logging</h2>
            <div class="endpoint">
                <p><span class="method">POST</span> /api/analytics</p>
                <p>Get analytics data</p>
            </div>

            <div class="endpoint">
                <p><span class="method">POST</span> /api/logs</p>
                <p>Get log entries</p>
            </div>

            <div class="endpoint">
                <p><span class="method">GET</span> /api/hub</p>
                <p>Get information about the Matter hub</p>
            </div>

            <h2>WebSocket Endpoints</h2>
            <div class="endpoint">
                <p><span class="method">WS</span> /ws/devices</p>
                <p>Real-time device updates</p>
            </div>

            <div class="endpoint">
                <p><span class="method">WS</span> /ws/logs</p>
                <p>Real-time log updates</p>
            </div>

            <div class="endpoint">
                <p><span class="method">WS</span> /ws/analytics</p>
                <p>Real-time analytics updates</p>
            </div>
        </body>
    </html>
    """

@app.post("/api/token", response_model=TokenResponse)
async def create_token(request: TokenRequest):
    # Create a new token
    expires_at = datetime.now(tz=datetime.timezone.utc) + timedelta(days=TOKEN_LIFETIME_DAYS)

    payload = {
        "sub": request.client_id,
        "name": request.client_name,
        "exp": expires_at
    }

    access_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_at": int(expires_at.timestamp())
    }

@app.post("/api/commission")
async def commission_device(request: CommissionRequest, user: Dict = Depends(get_current_user)):
    try:
        device_info = await controller.commission_device(request.setup_code, request.device_name)

        # Broadcast to WebSocket clients
        await broadcast_to_websockets("devices", {"event": "device_commissioned", "device": device_info})

        return device_info
    except Exception as e:
        logger.error(f"Failed to commission device: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/devices")
async def get_devices(user: Dict = Depends(get_current_user)):
    try:
        devices = await controller.get_devices()
        return devices
    except Exception as e:
        logger.error(f"Failed to get devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/devices/{device_id}")
async def remove_device(device_id: str, user: Dict = Depends(get_current_user)):
    try:
        success = await controller.remove_device(device_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove device")

        # Broadcast to WebSocket clients
        await broadcast_to_websockets("devices", {"event": "device_removed", "device_id": device_id})

        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to remove device: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/binding")
async def create_binding(request: BindingRequest, user: Dict = Depends(get_current_user)):
    try:
        success = await controller.create_binding(
            request.source_device_id,
            request.target_device_id,
            request.cluster_id
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create binding")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to create binding: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ota/update")
async def trigger_ota_update(request: OTAUpdateRequest, user: Dict = Depends(get_current_user)):
    try:
        success = await controller.trigger_ota_update(request.device_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to trigger OTA update")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to trigger OTA update: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analytics")
async def get_analytics(request: AnalyticsRequest, user: Dict = Depends(get_current_user)):
    try:
        analytics = await controller.get_analytics(
            request.start_time,
            request.end_time,
            request.event_types
        )
        return analytics
    except Exception as e:
        logger.error(f"Failed to get analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/logs")
async def get_logs(request: LogsRequest, user: Dict = Depends(get_current_user)):
    try:
        logs = await controller.get_logs(
            request.start_time,
            request.end_time,
            request.log_types,
            request.limit
        )
        return logs
    except Exception as e:
        logger.error(f"Failed to get logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hub")
async def get_hub_info(user: Dict = Depends(get_current_user)):
    try:
        hub_info = await controller.get_hub_info()
        return hub_info
    except Exception as e:
        logger.error(f"Failed to get hub info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoints
@app.websocket("/ws/devices")
async def websocket_devices(websocket: WebSocket):
    await websocket.accept()
    ws_connections["devices"].append(websocket)

    try:
        while True:
            # Wait for a message (ping)
            await websocket.receive_text()

            # Send the current device list
            devices = await controller.get_devices()
            await websocket.send_json({"devices": devices})
    except WebSocketDisconnect:
        ws_connections["devices"].remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in ws_connections["devices"]:
            ws_connections["devices"].remove(websocket)

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    ws_connections["logs"].append(websocket)

    try:
        while True:
            # Wait for a message (ping)
            await websocket.receive_text()

            # Send the latest logs
            logs = await controller.get_logs(limit=10)
            await websocket.send_json({"logs": logs})
    except WebSocketDisconnect:
        ws_connections["logs"].remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in ws_connections["logs"]:
            ws_connections["logs"].remove(websocket)

@app.websocket("/ws/analytics")
async def websocket_analytics(websocket: WebSocket):
    await websocket.accept()
    ws_connections["analytics"].append(websocket)

    try:
        while True:
            # Wait for a message (ping)
            await websocket.receive_text()

            # Send the latest analytics
            analytics = await controller.get_analytics()
            await websocket.send_json({"analytics": analytics})
    except WebSocketDisconnect:
        ws_connections["analytics"].remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in ws_connections["analytics"]:
            ws_connections["analytics"].remove(websocket)
