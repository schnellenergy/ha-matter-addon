import asyncio
import json
import websockets
from typing import Dict, Any, Optional, Callable
from logger import logger

class HomeAssistantWebsocketCollector:
    """Manages persistent WebSocket connection to Home Assistant Core event stream."""
    
    def __init__(
        self,
        ws_url: str,
        token: str,
        enricher: Any,
        event_callback: Callable[[Dict[str, Any]], None]
    ):
        self.ws_url = ws_url
        self.token = token
        self.enricher = enricher
        self.event_callback = event_callback
        
        self.msg_id = 1
        self.is_connected = False
        self._running = True

    def get_next_msg_id(self) -> int:
        self.msg_id += 1
        return self.msg_id

    async def connect_and_listen(self):
        """Infinite connection loop. Reconnects every 5 seconds on disconnect."""
        logger.info(f"Connecting to Home Assistant WebSocket at {self.ws_url}")
        
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    self.is_connected = True
                    # 1. Authenticate
                    auth_ok = await self._authenticate(websocket)
                    if not auth_ok:
                        logger.error("Authentication failed. Closing connection.")
                        self.is_connected = False
                        await asyncio.sleep(5)
                        continue
                        
                    logger.info("Successfully authenticated with Home Assistant WebSocket")
                    
                    # 2. Fetch registries
                    await self._fetch_ha_registries(websocket)
                    
                    # 3. Subscribe to events
                    await self._subscribe_to_events(websocket)
                    
                    # 4. Listen loop
                    await self._listen_loop(websocket)
                    
            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                self.is_connected = False
                logger.warning(f"WebSocket connection lost/failed: {e}. Reconnecting in 5 seconds...")
            except Exception as e:
                self.is_connected = False
                logger.error(f"Unexpected error in WebSocket collector: {e}. Reconnecting in 5 seconds...")
                
            await asyncio.sleep(5)

    async def _authenticate(self, websocket) -> bool:
        """Handles authentication handshake with HA Core."""
        # Wait for auth_required message
        raw_msg = await websocket.recv()
        msg = json.loads(raw_msg)
        if msg.get("type") != "auth_required":
            logger.error(f"Expected auth_required message, got: {msg}")
            return False
            
        # Send credentials
        await websocket.send(json.dumps({
            "type": "auth",
            "access_token": self.token
        }))
        
        # Wait for auth response
        raw_msg = await websocket.recv()
        msg = json.loads(raw_msg)
        if msg.get("type") == "auth_ok":
            return True
        else:
            logger.error(f"Auth response not ok: {msg}")
            return False

    async def _fetch_ha_registries(self, websocket):
        """Fetches Floors, Areas, Devices, and Entities registries to build cache maps."""
        logger.info("Fetching HA native registries...")
        
        try:
            # 1. Floor Registry
            floor_id = self.get_next_msg_id()
            await websocket.send(json.dumps({"id": floor_id, "type": "config/floor_registry/list"}))
            floor_resp = await websocket.recv()
            floors = json.loads(floor_resp).get("result", [])
            floor_map = {f["floor_id"]: f for f in floors if "floor_id" in f}
            
            # 2. Area Registry
            area_id = self.get_next_msg_id()
            await websocket.send(json.dumps({"id": area_id, "type": "config/area_registry/list"}))
            area_resp = await websocket.recv()
            areas = json.loads(area_resp).get("result", [])
            area_map = {a["area_id"]: a for a in areas if "area_id" in a}
            
            # 3. Device Registry
            dev_id = self.get_next_msg_id()
            await websocket.send(json.dumps({"id": dev_id, "type": "config/device_registry/list"}))
            dev_resp = await websocket.recv()
            devices = json.loads(dev_resp).get("result", [])
            device_map = {d["id"]: d for d in devices if "id" in d}
            
            # 4. Entity Registry
            ent_id = self.get_next_msg_id()
            await websocket.send(json.dumps({"id": ent_id, "type": "config/entity_registry/list"}))
            ent_resp = await websocket.recv()
            entities = json.loads(ent_resp).get("result", [])
            entity_map = {e["entity_id"]: e for e in entities if "entity_id" in e}
            
            # Update the event enricher cache
            self.enricher.update_ha_registries(
                entities=entity_map,
                devices=device_map,
                areas=area_map,
                floors=floor_map
            )
            logger.info(f"HA registries loaded. {len(entity_map)} entities, {len(device_map)} devices cached.")
            
        except Exception as e:
            logger.error(f"Error fetching HA registries: {e}. Enrichment will fall back to basic details.")

    async def _subscribe_to_events(self, websocket):
        """Subscribes to all event fires in Home Assistant Core."""
        sub_id = self.get_next_msg_id()
        await websocket.send(json.dumps({
            "id": sub_id,
            "type": "subscribe_events"
        }))
        
        # Confirm subscription was accepted
        raw_msg = await websocket.recv()
        msg = json.loads(raw_msg)
        if msg.get("success") is False:
            logger.error(f"Failed to subscribe to HA events: {msg}")
        else:
            logger.info("Successfully subscribed to Home Assistant events stream")

    async def _listen_loop(self, websocket):
        """Main loop that receives events from the websocket and invokes the callback."""
        while self._running:
            raw_msg = await websocket.recv()
            msg = json.loads(raw_msg)
            
            # Event messages have type 'event'
            if msg.get("type") == "event":
                event_data = msg.get("event", {})
                event_type = event_data.get("event_type")
                
                # Proactively trigger registry refresh if registries update
                if event_type in ("device_registry_updated", "entity_registry_updated", "area_registry_updated"):
                    logger.info(f"HA Registry update detected ({event_type}). Re-fetching registries...")
                    asyncio.create_task(self._fetch_ha_registries(websocket))
                    
                self.event_callback(event_data)

    def stop(self):
        """Gracefully signals the listener loop to stop."""
        self._running = False
