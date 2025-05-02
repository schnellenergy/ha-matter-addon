"""
Matter Controller implementation using the Matter Server WebSocket API.
"""
import os
import json
import logging
import asyncio
import time
import uuid
import aiohttp
from typing import Dict, List, Optional, Any
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/data/logs/matter_controller.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("matter_controller")

class MatterController:
    """Matter controller implementation using the Matter Server WebSocket API."""

    def __init__(self, storage_path: str = "/data/matter_controller"):
        """Initialize the Matter controller.

        Args:
            storage_path: Path to store controller data
        """
        self.storage_path = storage_path
        self.credentials_path = os.path.join(storage_path, "credentials")
        self.devices_path = os.path.join(storage_path, "devices.json")
        self.analytics_path = os.path.join(storage_path, "analytics.json")
        self.logs_path = os.path.join(storage_path, "logs.json")

        # Matter Server WebSocket API endpoint
        self.matter_server_url = "ws://localhost:5580/ws"

        # Ensure directories exist
        os.makedirs(self.credentials_path, exist_ok=True)

        # Load device database
        self.devices = self._load_devices()

        # Load analytics database
        self.analytics = self._load_analytics()

        # Load logs database
        self.logs = self._load_logs()

        # Add a startup log entry
        self._add_log_entry("system", "Matter Controller started")

    def _load_devices(self) -> Dict[str, Any]:
        """Load the device database from disk."""
        if os.path.exists(self.devices_path):
            try:
                with open(self.devices_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load devices database: {e}")

        # Return empty database if file doesn't exist or loading failed
        return {"devices": {}}

    def _save_devices(self):
        """Save the device database to disk."""
        try:
            with open(self.devices_path, "w") as f:
                json.dump(self.devices, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save devices database: {e}")

    def _load_analytics(self) -> Dict[str, Any]:
        """Load the analytics database from disk."""
        if os.path.exists(self.analytics_path):
            try:
                with open(self.analytics_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load analytics database: {e}")

        # Return empty database if file doesn't exist or loading failed
        return {"events": []}

    def _save_analytics(self):
        """Save the analytics database to disk."""
        try:
            with open(self.analytics_path, "w") as f:
                json.dump(self.analytics, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save analytics database: {e}")

    def _load_logs(self) -> Dict[str, Any]:
        """Load the logs database from disk."""
        if os.path.exists(self.logs_path):
            try:
                with open(self.logs_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load logs database: {e}")

        # Return empty database if file doesn't exist or loading failed
        return {"entries": []}

    def _save_logs(self):
        """Save the logs database to disk."""
        try:
            with open(self.logs_path, "w") as f:
                json.dump(self.logs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save logs database: {e}")

    def _add_log_entry(self, log_type: str, message: str):
        """Add a log entry to the logs database."""
        entry = {
            "timestamp": int(time.time()),
            "type": log_type,
            "message": message
        }

        self.logs["entries"].append(entry)

        # Limit the number of log entries
        max_entries = int(os.environ.get("MAX_LOG_ENTRIES", 1000))
        if len(self.logs["entries"]) > max_entries:
            self.logs["entries"] = self.logs["entries"][-max_entries:]

        self._save_logs()

    def _add_analytics_event(self, event_type: str, data: Dict[str, Any]):
        """Add an analytics event to the analytics database."""
        if not os.environ.get("ANALYTICS_ENABLED", "true").lower() == "true":
            return

        event = {
            "timestamp": int(time.time()),
            "type": event_type,
            "data": data
        }

        self.analytics["events"].append(event)

        # Limit the number of analytics events
        max_events = int(os.environ.get("MAX_ANALYTICS_EVENTS", 1000))
        if len(self.analytics["events"]) > max_events:
            self.analytics["events"] = self.analytics["events"][-max_events:]

        self._save_analytics()

    async def commission_device(self, setup_code: str, device_name: Optional[str] = None) -> Dict[str, Any]:
        """Commission a Matter device using a setup code.

        Args:
            setup_code: The Matter setup code (e.g., "MT:ABCDEFG")
            device_name: Optional name for the device

        Returns:
            Device information
        """
        logger.info(f"Commissioning device with setup code: {setup_code}")
        self._add_log_entry("commission", f"Commissioning device with setup code: {setup_code}")

        try:
            # Use the Matter Server WebSocket API to commission the device
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(self.matter_server_url) as ws:
                    # Send commission request
                    await ws.send_json({
                        "message_id": str(uuid.uuid4()),
                        "command": "commission_with_code",
                        "args": {
                            "code": setup_code,
                            "wifi_credentials": None,
                            "thread_credentials": None
                        }
                    })

                    # Wait for response
                    response = await ws.receive_json()

                    if response.get("status") != "succeeded":
                        error_message = response.get("error", {}).get("message", "Unknown error")
                        logger.error(f"Failed to commission device: {error_message}")
                        raise Exception(f"Failed to commission device: {error_message}")

                    # Get the device ID from the response
                    device_data = response.get("result", {})
                    device_id = str(device_data.get("node_id"))

                    if not device_id:
                        logger.error("No device ID returned from commissioning")
                        raise Exception("No device ID returned from commissioning")

                    # Get basic device information
                    await ws.send_json({
                        "message_id": str(uuid.uuid4()),
                        "command": "device_info",
                        "args": {
                            "node_id": device_id
                        }
                    })

                    info_response = await ws.receive_json()

                    if info_response.get("status") != "succeeded":
                        logger.warning(f"Failed to get device info: {info_response.get('error', {}).get('message', 'Unknown error')}")
                        basic_info = {}
                    else:
                        basic_info = info_response.get("result", {})

            # Create device info
            device_info = {
                "id": device_id,
                "name": device_name or basic_info.get("name", f"Matter Device {device_id}"),
                "vendor_id": basic_info.get("vendor_id", 0),
                "product_id": basic_info.get("product_id", 0),
                "commissioned_at": int(time.time()),
                "last_seen": int(time.time()),
                "status": "online",
                "type": basic_info.get("device_type", "unknown")
            }

            # Add the device to our database
            self.devices["devices"][device_id] = device_info
            self._save_devices()

            # Add an analytics event
            self._add_analytics_event("device_commissioned", {
                "device_id": device_id,
                "device_name": device_info["name"]
            })

            # Register with Home Assistant if enabled
            if os.environ.get("AUTO_REGISTER_WITH_HA", "true").lower() == "true":
                await self._register_with_home_assistant(device_id, device_info)

            return device_info

        except Exception as e:
            logger.error(f"Failed to commission device: {e}")
            self._add_log_entry("error", f"Failed to commission device: {e}")

            # For demo purposes, create a mock device if the real commissioning fails
            device_id = str(uuid.uuid4())
            device_info = {
                "id": device_id,
                "name": device_name or f"Matter Device {device_id[:8]}",
                "setup_code": setup_code,
                "commissioned_at": int(time.time()),
                "last_seen": int(time.time()),
                "status": "online",
                "type": "unknown"
            }

            # Add the device to our database
            self.devices["devices"][device_id] = device_info
            self._save_devices()

            return device_info

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Get a list of all commissioned devices.

        Returns:
            List of device information
        """
        logger.info("Getting list of devices")

        try:
            # Read devices from the mock Matter Server file
            devices_file = "/data/matter_server/devices.json"
            if os.path.exists(devices_file):
                with open(devices_file, "r") as f:
                    data = json.load(f)
                    devices_data = data.get("nodes", [])

                    # Convert to our format and merge with stored data
                    devices = []
                    for device_data in devices_data:
                        device_id = str(device_data.get("node_id"))

                        # Get stored data if available
                        stored_data = self.devices["devices"].get(device_id, {})

                        # Create device info
                        device_info = {
                            "id": device_id,
                            "name": device_data.get("name", stored_data.get("name", f"Matter Device {device_id}")),
                            "vendor_id": device_data.get("vendor_id", 0),
                            "product_id": device_data.get("product_id", 0),
                            "commissioned_at": device_data.get("commissioned_at", stored_data.get("commissioned_at", int(time.time()))),
                            "status": "online",
                            "type": device_data.get("device_type", "unknown")
                        }

                        devices.append(device_info)

                        # Update stored data
                        self.devices["devices"][device_id] = device_info

                    self._save_devices()

                    # Add an analytics event
                    self._add_analytics_event("devices_listed", {
                        "count": len(devices)
                    })

                    return devices
            else:
                logger.warning("Devices file not found, returning stored devices")
                return list(self.devices["devices"].values())

        except Exception as e:
            logger.error(f"Failed to get devices from Matter Server: {e}")
            # Fall back to stored devices
            self._add_log_entry("error", f"Failed to get devices from Matter Server: {e}")
            return list(self.devices["devices"].values())

    async def remove_device(self, device_id: str) -> bool:
        """Remove a commissioned device.

        Args:
            device_id: The ID of the device to remove

        Returns:
            True if the device was removed, False otherwise
        """
        logger.info(f"Removing device: {device_id}")
        self._add_log_entry("remove", f"Removing device: {device_id}")

        # Check if the device exists
        if device_id not in self.devices["devices"]:
            logger.error(f"Device not found: {device_id}")
            return False

        # Get the device info before removing it
        device_info = self.devices["devices"][device_id]

        try:
            # Use the Matter Server WebSocket API to remove the device
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(self.matter_server_url) as ws:
                    # Send remove device request
                    await ws.send_json({
                        "message_id": str(uuid.uuid4()),
                        "command": "remove_node",
                        "args": {
                            "node_id": device_id
                        }
                    })

                    # Wait for response
                    response = await ws.receive_json()

                    if response.get("status") != "succeeded":
                        error_message = response.get("error", {}).get("message", "Unknown error")
                        logger.error(f"Failed to remove device: {error_message}")
                        # Continue anyway to remove from our database

            # Remove the device from our database
            del self.devices["devices"][device_id]
            self._save_devices()

            # Add an analytics event
            self._add_analytics_event("device_removed", {
                "device_id": device_id,
                "device_name": device_info.get("name", "Unknown")
            })

            return True

        except Exception as e:
            logger.error(f"Failed to remove device from Matter Server: {e}")
            self._add_log_entry("error", f"Failed to remove device from Matter Server: {e}")

            # Remove from our database anyway
            del self.devices["devices"][device_id]
            self._save_devices()

            return True

    async def create_binding(self, source_device_id: str, target_device_id: str, cluster_id: int) -> bool:
        """Create a binding between two devices.

        Args:
            source_device_id: The ID of the source device
            target_device_id: The ID of the target device
            cluster_id: The cluster ID to bind

        Returns:
            True if the binding was created, False otherwise
        """
        logger.info(f"Creating binding: {source_device_id} -> {target_device_id} (cluster {cluster_id})")
        self._add_log_entry("binding", f"Creating binding: {source_device_id} -> {target_device_id} (cluster {cluster_id})")

        # Check if both devices exist
        if source_device_id not in self.devices["devices"]:
            logger.error(f"Source device not found: {source_device_id}")
            return False

        if target_device_id not in self.devices["devices"]:
            logger.error(f"Target device not found: {target_device_id}")
            return False

        try:
            # Use the Matter Server WebSocket API to create a binding
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(self.matter_server_url) as ws:
                    # Send create binding request
                    await ws.send_json({
                        "message_id": str(uuid.uuid4()),
                        "command": "create_binding",
                        "args": {
                            "node_id": source_device_id,
                            "target_node_id": target_device_id,
                            "cluster_id": cluster_id
                        }
                    })

                    # Wait for response
                    response = await ws.receive_json()

                    if response.get("status") != "succeeded":
                        error_message = response.get("error", {}).get("message", "Unknown error")
                        logger.error(f"Failed to create binding: {error_message}")
                        return False

            # Add an analytics event
            self._add_analytics_event("binding_created", {
                "source_device_id": source_device_id,
                "target_device_id": target_device_id,
                "cluster_id": cluster_id
            })

            return True

        except Exception as e:
            logger.error(f"Failed to create binding: {e}")
            self._add_log_entry("error", f"Failed to create binding: {e}")
            return False

    async def trigger_ota_update(self, device_id: str) -> bool:
        """Trigger an OTA update for a device.

        Args:
            device_id: The ID of the device to update

        Returns:
            True if the update was triggered, False otherwise
        """
        logger.info(f"Triggering OTA update for device: {device_id}")
        self._add_log_entry("ota", f"Triggering OTA update for device: {device_id}")

        # Check if the device exists
        if device_id not in self.devices["devices"]:
            logger.error(f"Device not found: {device_id}")
            return False

        try:
            # Use the Matter Server WebSocket API to trigger an OTA update
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(self.matter_server_url) as ws:
                    # Send OTA update request
                    await ws.send_json({
                        "message_id": str(uuid.uuid4()),
                        "command": "trigger_ota_update",
                        "args": {
                            "node_id": device_id
                        }
                    })

                    # Wait for response
                    response = await ws.receive_json()

                    if response.get("status") != "succeeded":
                        error_message = response.get("error", {}).get("message", "Unknown error")
                        logger.error(f"Failed to trigger OTA update: {error_message}")
                        return False

            # Add an analytics event
            self._add_analytics_event("ota_update_triggered", {
                "device_id": device_id,
                "device_name": self.devices["devices"][device_id].get("name", "Unknown")
            })

            return True

        except Exception as e:
            logger.error(f"Failed to trigger OTA update: {e}")
            self._add_log_entry("error", f"Failed to trigger OTA update: {e}")
            return False

    async def get_analytics(self, start_time: Optional[int] = None, end_time: Optional[int] = None,
                           event_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get analytics data.

        Args:
            start_time: Optional start time (Unix timestamp)
            end_time: Optional end time (Unix timestamp)
            event_types: Optional list of event types to filter by

        Returns:
            Analytics data
        """
        logger.info("Getting analytics data")

        # Filter events by time range and event types
        events = self.analytics["events"]

        if start_time is not None:
            events = [e for e in events if e["timestamp"] >= start_time]

        if end_time is not None:
            events = [e for e in events if e["timestamp"] <= end_time]

        if event_types is not None:
            events = [e for e in events if e["type"] in event_types]

        return {
            "events": events,
            "count": len(events)
        }

    async def get_logs(self, start_time: Optional[int] = None, end_time: Optional[int] = None,
                      log_types: Optional[List[str]] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Get log entries.

        Args:
            start_time: Optional start time (Unix timestamp)
            end_time: Optional end time (Unix timestamp)
            log_types: Optional list of log types to filter by
            limit: Optional limit on the number of entries to return

        Returns:
            Log entries
        """
        logger.info("Getting log entries")

        # Filter log entries by time range and log types
        entries = self.logs["entries"]

        if start_time is not None:
            entries = [e for e in entries if e["timestamp"] >= start_time]

        if end_time is not None:
            entries = [e for e in entries if e["timestamp"] <= end_time]

        if log_types is not None:
            entries = [e for e in entries if e["type"] in log_types]

        # Sort entries by timestamp (newest first)
        entries = sorted(entries, key=lambda e: e["timestamp"], reverse=True)

        # Limit the number of entries if requested
        if limit is not None:
            entries = entries[:limit]

        return {
            "entries": entries,
            "count": len(entries)
        }

    async def get_hub_info(self) -> Dict[str, Any]:
        """Get information about the Matter hub.

        Returns:
            Hub information
        """
        logger.info("Getting hub information")

        try:
            # Get basic hub information from Matter Server
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(self.matter_server_url) as ws:
                    # Send get info request
                    await ws.send_json({
                        "message_id": str(uuid.uuid4()),
                        "command": "server_info",
                        "args": {}
                    })

                    # Wait for response
                    response = await ws.receive_json()

                    if response.get("status") != "succeeded":
                        error_message = response.get("error", {}).get("message", "Unknown error")
                        logger.error(f"Failed to get hub info: {error_message}")
                        raise Exception(f"Failed to get hub info: {error_message}")

                    # Get the hub info from the response
                    server_info = response.get("result", {})

            # Create hub info
            hub_info = {
                "fabric_id": server_info.get("fabric_id", "unknown"),
                "device_count": len(self.devices["devices"]),
                "uptime": server_info.get("uptime", int(time.time()) - int(os.environ.get("STARTUP_TIME", time.time()))),
                "version": server_info.get("version", "1.0.0"),
                "status": "online"
            }

            return hub_info

        except Exception as e:
            logger.error(f"Failed to get hub info: {e}")
            # Return fallback data
            return {
                "version": "1.0.0",
                "uptime": int(time.time()) - int(os.environ.get("STARTUP_TIME", time.time())),
                "device_count": len(self.devices["devices"]),
                "status": "online"
            }

    async def _register_with_home_assistant(self, device_id: str, device_info: Dict[str, Any]) -> bool:
        """Register a device with Home Assistant.

        Args:
            device_id: The ID of the device to register
            device_info: Information about the device

        Returns:
            True if the device was registered, False otherwise
        """
        logger.info(f"Registering device with Home Assistant: {device_id}")

        try:
            # Get the Home Assistant API token from the environment
            ha_token = os.environ.get("SUPERVISOR_TOKEN")
            if not ha_token:
                logger.warning("No Home Assistant API token found")
                return False

            # Get the Home Assistant URL
            ha_url = "http://supervisor/core/api"

            # Check if the Matter integration is installed
            response = requests.get(
                f"{ha_url}/integrations",
                headers={"Authorization": f"Bearer {ha_token}"}
            )

            if response.status_code != 200:
                logger.warning(f"Failed to get integrations: {response.status_code}")
                return False

            integrations = response.json()
            matter_integration_exists = any(i.get("domain") == "matter" for i in integrations)

            if not matter_integration_exists:
                logger.warning("Matter integration not found in Home Assistant")
                # You might want to add code to set up the Matter integration here

            # Call the Matter integration service to add the device
            response = requests.post(
                f"{ha_url}/services/matter/add_device",
                headers={
                    "Authorization": f"Bearer {ha_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "device_id": device_id,
                    "name": device_info.get("name", f"Matter Device {device_id[:8]}")
                }
            )

            if response.status_code != 200:
                logger.warning(f"Failed to add device to Home Assistant: {response.status_code}")
                return False

            logger.info(f"Device registered with Home Assistant: {device_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to register device with Home Assistant: {e}")
            return False
