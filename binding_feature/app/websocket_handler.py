import asyncio
import websockets
import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any
from database import db_manager

logger = logging.getLogger(__name__)

class HomeAssistantWebSocketClient:
    def __init__(self):
        self.websocket = None
        self.ha_token = os.getenv("HA_TOKEN", "")
        self.ha_url = "ws://supervisor/core/websocket"  # Internal supervisor URL
        self.message_id = 1
        self.is_connected = False
        self.reconnect_interval = 30
        
    async def connect(self):
        """Connect to Home Assistant WebSocket API"""
        try:
            if not self.ha_token:
                logger.warning("No HA token provided, WebSocket integration disabled")
                return False
                
            logger.info(f"Connecting to Home Assistant WebSocket: {self.ha_url}")
            self.websocket = await websockets.connect(self.ha_url)
            
            # Receive auth required message
            auth_required = await self.websocket.recv()
            auth_data = json.loads(auth_required)
            
            if auth_data.get("type") != "auth_required":
                logger.error("Unexpected auth message from HA")
                return False
            
            # Send authentication
            auth_message = {
                "type": "auth",
                "access_token": self.ha_token
            }
            await self.websocket.send(json.dumps(auth_message))
            
            # Receive auth result
            auth_result = await self.websocket.recv()
            auth_data = json.loads(auth_result)
            
            if auth_data.get("type") == "auth_ok":
                logger.info("Successfully authenticated with Home Assistant")
                self.is_connected = True
                return True
            else:
                logger.error(f"Authentication failed: {auth_data}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to Home Assistant: {e}")
            return False
    
    async def subscribe_to_events(self):
        """Subscribe to Home Assistant events"""
        if not self.is_connected:
            return
            
        try:
            # Subscribe to state changes
            subscribe_message = {
                "id": self.message_id,
                "type": "subscribe_events",
                "event_type": "state_changed"
            }
            await self.websocket.send(json.dumps(subscribe_message))
            self.message_id += 1
            
            # Subscribe to automation events
            automation_message = {
                "id": self.message_id,
                "type": "subscribe_events",
                "event_type": "automation_triggered"
            }
            await self.websocket.send(json.dumps(automation_message))
            self.message_id += 1
            
            # Subscribe to scene events
            scene_message = {
                "id": self.message_id,
                "type": "subscribe_events",
                "event_type": "scene_activated"
            }
            await self.websocket.send(json.dumps(scene_message))
            self.message_id += 1
            
            logger.info("Subscribed to Home Assistant events")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to events: {e}")
    
    async def listen_for_events(self):
        """Listen for and process Home Assistant events"""
        try:
            while self.is_connected:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                if data.get("type") == "event":
                    await self.process_event(data.get("event", {}))
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error listening for events: {e}")
            self.is_connected = False
    
    async def process_event(self, event: Dict[str, Any]):
        """Process incoming Home Assistant events"""
        try:
            event_type = event.get("event_type")
            event_data = event.get("data", {})
            
            if event_type == "state_changed":
                await self.process_state_change(event_data)
            elif event_type == "automation_triggered":
                await self.process_automation_event(event_data)
            elif event_type == "scene_activated":
                await self.process_scene_event(event_data)
                
        except Exception as e:
            logger.error(f"Error processing event: {e}")
    
    async def process_state_change(self, data: Dict[str, Any]):
        """Process state change events"""
        try:
            entity_id = data.get("entity_id")
            new_state = data.get("new_state", {})
            old_state = data.get("old_state", {})
            
            if not entity_id or not new_state:
                return
            
            # Extract device information
            device_type = entity_id.split(".")[0]
            state_value = new_state.get("state")
            attributes = new_state.get("attributes", {})
            
            # Store device analytics
            async with db_manager.get_connection() as db:
                await db.execute("""
                    INSERT INTO device_analytics 
                    (device_id, device_name, device_type, metric_type, metric_value, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    entity_id,
                    attributes.get("friendly_name", entity_id),
                    device_type,
                    "state_change",
                    state_value,
                    datetime.now()
                ))
                await db.commit()
            
            # Calculate and store reliability metrics
            if old_state and old_state.get("state") != state_value:
                await self.update_reliability_metrics(entity_id, state_value, attributes)
                
        except Exception as e:
            logger.error(f"Error processing state change: {e}")
    
    async def process_automation_event(self, data: Dict[str, Any]):
        """Process automation triggered events"""
        try:
            automation_id = data.get("entity_id", "")
            automation_name = data.get("name", "")
            trigger = data.get("trigger", {})
            
            async with db_manager.get_connection() as db:
                await db.execute("""
                    INSERT INTO automation_analytics 
                    (automation_id, automation_name, trigger_type, trigger_details, success, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    automation_id,
                    automation_name,
                    trigger.get("platform", "unknown"),
                    json.dumps(trigger),
                    True,
                    datetime.now()
                ))
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error processing automation event: {e}")
    
    async def process_scene_event(self, data: Dict[str, Any]):
        """Process scene activated events"""
        try:
            scene_id = data.get("entity_id", "")
            scene_name = data.get("name", "")
            
            async with db_manager.get_connection() as db:
                await db.execute("""
                    INSERT INTO scene_analytics 
                    (scene_id, scene_name, activation_method, success, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    scene_id,
                    scene_name,
                    "websocket_event",
                    True,
                    datetime.now()
                ))
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error processing scene event: {e}")
    
    async def update_reliability_metrics(self, entity_id: str, state: str, attributes: Dict[str, Any]):
        """Update reliability metrics for a device"""
        try:
            # Determine if device is online/offline
            is_online = state not in ["unavailable", "unknown", "off"]
            
            async with db_manager.get_connection() as db:
                # Get last reliability record
                cursor = await db.execute("""
                    SELECT * FROM reliability_metrics 
                    WHERE device_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT 1
                """, (entity_id,))
                last_record = await cursor.fetchone()
                
                # Calculate uptime percentage (simplified)
                uptime_percentage = 100.0 if is_online else 0.0
                if last_record:
                    # You can implement more sophisticated uptime calculation here
                    pass
                
                # Insert new reliability record
                await db.execute("""
                    INSERT INTO reliability_metrics 
                    (device_id, device_name, uptime_percentage, last_seen, status, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    entity_id,
                    attributes.get("friendly_name", entity_id),
                    uptime_percentage,
                    datetime.now(),
                    "online" if is_online else "offline",
                    datetime.now()
                ))
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error updating reliability metrics: {e}")
    
    async def disconnect(self):
        """Disconnect from Home Assistant WebSocket"""
        self.is_connected = False
        if self.websocket:
            await self.websocket.close()
            logger.info("Disconnected from Home Assistant WebSocket")

class WebSocketManager:
    def __init__(self):
        self.client = HomeAssistantWebSocketClient()
        self.running = False
    
    async def start(self):
        """Start WebSocket client with auto-reconnect"""
        self.running = True
        
        while self.running:
            try:
                if await self.client.connect():
                    await self.client.subscribe_to_events()
                    await self.client.listen_for_events()
                else:
                    logger.warning("Failed to connect, retrying in 30 seconds...")
                    
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            
            if self.running:
                await asyncio.sleep(self.client.reconnect_interval)
    
    async def stop(self):
        """Stop WebSocket client"""
        self.running = False
        await self.client.disconnect()

# Global WebSocket manager instance
websocket_manager = WebSocketManager()
