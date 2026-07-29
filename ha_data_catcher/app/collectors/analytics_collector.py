import os
import json
import logging
import asyncio
import datetime
import requests
import websockets

logger = logging.getLogger(__name__)

CUSTOM_CLUSTER_ID = 0x130AFF01

class AnalyticsCollector:
    def __init__(self, matter_ws_url="ws://core-matter-server:5580/ws", custom_storage_url="http://localhost:8100", webhook_url="", enricher=None):
        self.matter_ws_url = matter_ws_url
        self.custom_storage_url = custom_storage_url
        self.webhook_url = webhook_url
        self.enricher = enricher

    async def fetch_matter_nodes(self):
        try:
            async with websockets.connect(self.matter_ws_url) as websocket:
                await websocket.send(json.dumps({"message_id": 1, "command": "get_nodes"}))
                
                # Loop to skip initial welcome messages and wait for the actual response
                for _ in range(5):
                    response = await websocket.recv()
                    data = json.loads(response)
                    
                    if data.get("message_id") == 1 and "result" in data:
                        return data["result"]
        except Exception as e:
            logger.error(f"Error connecting to Matter Server WebSocket: {e}")
        return []

    def fetch_custom_metadata(self):
        docks = {}
        snaps = {}
        room_map = {}
        try:
            resp = requests.get(f"{self.custom_storage_url}/api/data/device_setup", timeout=5)
            if resp.status_code == 200:
                body = resp.json()
                val = body.get("value") or body.get("data") or body
                if isinstance(val, str):
                    try: val = json.loads(val)
                    except: val = {}
                struct = val.get("structure") if isinstance(val, dict) and "structure" in val else val
                
                docks = struct.get("docks", {}) if isinstance(struct, dict) else {}
                snaps = struct.get("snaps", {}) if isinstance(struct, dict) else {}
            
            resp2 = requests.get(f"{self.custom_storage_url}/api/data/home_setup", timeout=5)
            if resp2.status_code == 200:
                body = resp2.json()
                val = body.get("value") or body.get("data") or body
                if isinstance(val, str):
                    try: val = json.loads(val)
                    except: val = {}
                struct = val.get("structure") if isinstance(val, dict) and "structure" in val else val
                
                home_data = struct if isinstance(struct, dict) else {}
                for fl in home_data.get("floors", []):
                    for rm in fl.get("rooms", []):
                        r_id = rm.get("room_id") or rm.get("id")
                        if r_id:
                            room_map[r_id] = {"name": rm.get("name"), "floor_name": fl.get("name")}
        except Exception as e:
            logger.error(f"Error fetching custom metadata: {e}")
        
        return docks, snaps, room_map

    def match_node_id(self, matter_id, metadata_id):
        if matter_id is None or metadata_id is None:
            return False
        ha_str = str(matter_id).strip().lower()
        custom_str = str(metadata_id).strip().lower()
        if ha_str == custom_str:
            return True
            
        def extract_node_id(s: str):
            import re
            
            # If it's a HA Matter identifier: deviceid_...-1-60 (the last part is HEX)
            if s.startswith("deviceid_"):
                parts = s.split('-')
                if len(parts) >= 2:
                    try:
                        return int(parts[-1], 16)
                    except ValueError:
                        pass
            
            # Otherwise, try extracting the last numeric part as decimal
            match = re.search(r'(\d+)\s*$', s)
            if match:
                try:
                    return int(match.group(1), 10)
                except ValueError:
                    pass
            return None
            
        ha_num = extract_node_id(ha_str)
        custom_num = extract_node_id(custom_str)
        if ha_num is not None and custom_num is not None and ha_num == custom_num:
            return True
        return False

    async def run_sync(self, hub_mac):
        if not self.webhook_url:
            logger.info("Analytics sync skipped: No GOOGLE_WEBHOOK_URL configured.")
            return

        logger.info("Starting Matter Server analytics sync...")
        
        nodes = await self.fetch_matter_nodes()
        docks, snaps, room_map = self.fetch_custom_metadata()
        last_updated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rows_array = []

        for node in nodes:
            node_id = node.get("node_id")
            entity_id = f"node_{node_id}"
            
            dock_match = None
            snap_match = None

            for d_id, d_data in docks.items():
                if self.match_node_id(node_id, d_data.get("matter_node_id")) or str(d_data.get("entity_id")) == entity_id:
                    dock_match = {"id": d_id, "data": d_data}
                    break
                
                # Recursive fallback for docklets
                if self.enricher:
                    docklets = d_data.get("docklets", [])
                    matched = False
                    items = docklets if isinstance(docklets, list) else list(docklets.values()) if isinstance(docklets, dict) else []
                    for item in items:
                        e_id = item.get("entityId") or item.get("entity_id")
                        if e_id:
                            resolved = self.enricher.resolve_matter_node_id(entity_id=e_id)
                            logger.info(f"[Debug] Checking docklet e_id='{e_id}' -> resolved matter_node_id='{resolved}' (comparing with node_id='{node_id}')")
                            if resolved and self.match_node_id(node_id, resolved):
                                dock_match = {"id": d_id, "data": d_data}
                                matched = True
                                logger.info(f"[Debug] SUCCESSFULLY matched dock {d_id} to node {node_id} via docklet entity {e_id}")
                                break
                    if matched:
                        break
            
            if not dock_match:
                for s_id, s_data in snaps.items():
                    if self.match_node_id(node_id, s_data.get("matter_node_id")) or str(s_data.get("entity_id")) == entity_id:
                        snap_match = {"id": s_id, "data": s_data}
                        break
                        
                    # Recursive fallback for sub_devices
                    if self.enricher:
                        sub_devices = s_data.get("sub_devices", s_data.get("subDevices", []))
                        matched = False
                        for item in sub_devices:
                            e_id = item.get("entity_id")
                            if e_id:
                                resolved = self.enricher.resolve_matter_node_id(entity_id=e_id)
                                if resolved and self.match_node_id(node_id, resolved):
                                    snap_match = {"id": s_id, "data": s_data}
                                    matched = True
                                    break
                        if matched:
                            break
            
            device_type = "matter_node"
            dock_or_snap_id = ""
            node_label = ""
            room_name = ""
            floor_name = ""

            if dock_match:
                device_type = "dock"
                dock_or_snap_id = dock_match["id"]
                node_label = dock_match["data"].get("label", dock_match["data"].get("name", "Bed room Dock"))
                room_id = dock_match["data"].get("room_id") or dock_match["data"].get("roomId")
                if room_id and room_id in room_map:
                    room_name = room_map[room_id]["name"]
                    floor_name = room_map[room_id]["floor_name"]
            elif snap_match:
                device_type = snap_match["data"].get("type", "snap")
                dock_or_snap_id = snap_match["id"]
                node_label = snap_match["data"].get("label", snap_match["data"].get("name", f"Snap {node_id}"))
                room_id = snap_match["data"].get("room_id") or snap_match["data"].get("roomId")
                if room_id and room_id in room_map:
                    room_name = room_map[room_id]["name"]
                    floor_name = room_map[room_id]["floor_name"]

            attributes = node.get("attributes", {})

            for ep in range(1, 7):
                def get_attr(attr_id):
                    return attributes.get(f"{ep}/{CUSTOM_CLUSTER_ID}/{attr_id}", 0)

                is_bound = any(k.startswith(f"{ep}/30/") for k in attributes.keys())

                docklet_id = ""
                docklet_label = ""
                bound_device_label = ""
                bound_device_entity_id = ""

                if dock_match:
                    d_data = dock_match["data"]
                    matched_docklet = None
                    docklets = d_data.get("docklets", [])
                    if isinstance(docklets, list):
                        for item in docklets:
                            if str(item.get("position")) == str(ep) or str(item.get("id")) == f"docklet_{ep}":
                                matched_docklet = item
                                break
                    elif isinstance(docklets, dict):
                        for k, item in docklets.items():
                            if str(item.get("position")) == str(ep) or k == f"docklet_{ep}" or str(item.get("id")) == f"docklet_{ep}":
                                matched_docklet = item
                                break
                    
                    if matched_docklet:
                        docklet_id = matched_docklet.get("id", matched_docklet.get("entityId", matched_docklet.get("entity_id", f"docklet_{ep}")))
                        docklet_label = matched_docklet.get("name", matched_docklet.get("boundDeviceLabel", matched_docklet.get("bound_device_label", f"Button {ep}")))
                        bound_device_label = matched_docklet.get("boundDeviceLabel", matched_docklet.get("bound_device_label", matched_docklet.get("name", "not_mapped")))
                        bound_device_entity_id = matched_docklet.get("boundDeviceEntityId", matched_docklet.get("bound_device_entity_id", matched_docklet.get("entityId", matched_docklet.get("entity_id", ""))))
                elif snap_match:
                    s_data = snap_match["data"]
                    sub_devices = s_data.get("sub_devices", s_data.get("subDevices", []))
                    matched_subdev = None
                    for item in sub_devices:
                        if str(item.get("position")) == str(ep) or str(item.get("endpoint")) == str(ep) or str(item.get("endpoint_id")) == str(ep):
                            matched_subdev = item
                            break
                    if matched_subdev:
                        docklet_id = matched_subdev.get("id", matched_subdev.get("entity_id", ""))
                        docklet_label = matched_subdev.get("name", matched_subdev.get("label", f"Channel {ep}"))
                        bound_device_label = matched_subdev.get("name", matched_subdev.get("label", ""))
                        bound_device_entity_id = matched_subdev.get("entity_id", "")

                row_data = [
                    last_updated,
                    hub_mac,
                    entity_id,
                    device_type,
                    dock_or_snap_id,
                    node_label,
                    room_name,
                    floor_name,
                    f"endpoint_{ep}",
                    docklet_id,
                    docklet_label,
                    bound_device_label,
                    bound_device_entity_id,
                    "TRUE" if is_bound else "FALSE",
                    str(get_attr(2)),
                    str(get_attr(3)),
                    str(get_attr(4)),
                    str(get_attr(5))
                ]
                
                rows_array.push(row_data) if hasattr(rows_array, 'push') else rows_array.append(row_data)

        if len(rows_array) > 0:
            try:
                resp = requests.post(self.webhook_url, json={"rows": rows_array}, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"Successfully synced {len(rows_array)} node endpoint rows to Google Sheets.")
                else:
                    logger.error(f"Google Sheets sync failed with status {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Failed to push to Google Sheets: {e}")
        else:
            logger.info("No nodes found, skipping Google Sheets push.")

    def run_sync_sync(self, hub_mac):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(self.run_sync(hub_mac))
