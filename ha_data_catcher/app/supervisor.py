import os
import json
import requests
from typing import Dict, Any, Optional
from logger import logger

class SupervisorClient:
    """Client for interacting with the Home Assistant Supervisor API."""
    
    def __init__(self):
        self.api_url = os.getenv("SUPERVISOR_API", "http://supervisor")
        self.token = os.getenv("SUPERVISOR_TOKEN", "")
        self.is_supervisor = bool(self.token)
        
        if self.is_supervisor:
            logger.info("Running in Home Assistant Supervisor environment")
        else:
            logger.warning("Supervisor token not found. Running in standalone/local mode")

    def get_headers(self) -> Dict[str, str]:
        """Generate Authorization headers for Supervisor API requests."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get_ha_details(self, fallback_token: str = "") -> Dict[str, Any]:
        """Discovers the IP, Port, and WebSocket URI of HA Core."""
        details = {
            "ha_ip": "homeassistant",
            "ha_port": 8123,
            "ws_url": "ws://homeassistant:8123/api/websocket",
            "token": self.token or fallback_token
        }
        
        if self.is_supervisor:
            # Inside supervisor network, we query /core/info
            try:
                url = f"{self.api_url}/core/info"
                response = requests.get(url, headers=self.get_headers(), timeout=5)
                if response.status_code == 200:
                    data = response.json().get("data", {})
                    port = data.get("port", 8123)
                    ssl = data.get("ssl", False)
                    
                    details["ha_port"] = port
                    # The supervisor itself provides a proxy websocket path
                    details["ws_url"] = f"ws://supervisor/core/websocket"
                    logger.info(f"Discovered Home Assistant Core on port {port} (SSL: {ssl})")
                else:
                    logger.warning(f"Could not retrieve Core info, status code: {response.status_code}")
            except Exception as e:
                logger.error(f"Error querying Supervisor core/info: {e}")
        else:
            # Standalone/fallback mode (no supervisor token)
            # If running locally on developer PC, we can override via env
            env_ha_ip = os.getenv("HA_IP")
            if env_ha_ip:
                details["ha_ip"] = env_ha_ip
                details["ws_url"] = f"ws://{env_ha_ip}:8123/api/websocket"
            else:
                # Default to the internal HA container DNS name in HA network
                details["ha_ip"] = "homeassistant"
                details["ws_url"] = "ws://homeassistant:8123/api/websocket"
            
            logger.info(f"Using Home Assistant Core connection: {details['ws_url']}")

        # Let's try to discover the network IP of the hub if supervisor is active
        if self.is_supervisor:
            try:
                url = f"{self.api_url}/network/info"
                response = requests.get(url, headers=self.get_headers(), timeout=5)
                if response.status_code == 200:
                    interfaces = response.json().get("data", {}).get("interfaces", [])
                    for interface in interfaces:
                        if interface.get("enabled"):
                            ipv4 = interface.get("ipv4", {})
                            address = ipv4.get("address", [])
                            if address:
                                # Extract clean IP without subnet mask
                                ip = address[0].split("/")[0]
                                details["ha_ip"] = ip
                                logger.info(f"Discovered hub primary interface IP: {ip}")
                                break
            except Exception as e:
                logger.debug(f"Could not query Supervisor network/info (normal in some setups): {e}")

        return details

    def discover_hub_id(self, custom_storage_url: str) -> str:
        """Attempts to auto-discover the hub ID."""
        # 1. Check Custom Data Storage home_setup
        try:
            # Format custom_storage_url properly
            base_url = custom_storage_url.rstrip("/")
            url = f"{base_url}/api/data/home_setup"
            logger.debug(f"Attempting to query Custom Storage at {url} for hub ID")
            
            # Since Custom Data Storage might have api_key, we check env
            headers = {}
            api_key = os.getenv("CUSTOM_STORAGE_API_KEY", "")
            if api_key:
                headers["X-API-Key"] = api_key
                
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                body = response.json()
                if body.get("success"):
                    val = body.get("value")
                    if isinstance(val, str):
                        val = json.loads(val)
                    if isinstance(val, dict):
                        home_id = val.get("home_id") or val.get("home_automation", {}).get("home_id")
                        if home_id:
                            logger.info(f"Auto-discovered hub_id from Custom Data Storage: {home_id}")
                            return str(home_id)
        except Exception as e:
            logger.warning(f"Could not fetch hub_id from Custom Data Storage: {e}")

        # 2. Try Supervisor host/info for hostname
        if self.is_supervisor:
            try:
                url = f"{self.api_url}/host/info"
                response = requests.get(url, headers=self.get_headers(), timeout=5)
                if response.status_code == 200:
                    data = response.json().get("data", {})
                    hostname = data.get("hostname", "")
                    if hostname:
                        # Clean up hostname
                        hub_id = hostname.upper().replace("-", "_")
                        logger.info(f"Auto-discovered hub_id from host hostname: {hub_id}")
                        return hub_id
            except Exception as e:
                logger.warning(f"Could not fetch hub_id from Host Info: {e}")

        # 3. Fallback to machine ID or default
        try:
            if os.path.exists("/etc/machine-id"):
                with open("/etc/machine-id", "r") as f:
                    machine_id = f.read().strip()[:8].upper()
                    hub_id = f"HUB_{machine_id}"
                    logger.info(f"Auto-discovered hub_id from machine-id: {hub_id}")
                    return hub_id
        except Exception:
            pass

        logger.warning("Hub ID auto-discovery failed. Defaulting to HUB_UNKNOWN")
        return "HUB_UNKNOWN"

    def get_ha_timezone(self) -> str:
        """Discovers the Home Assistant configured timezone."""
        fallback = "Asia/Kolkata"
        if not self.is_supervisor:
            tz = os.getenv("TZ", fallback)
            if tz == "UTC":
                tz = "Asia/Kolkata"
            return tz
            
        try:
            # We can query HA REST API config via supervisor proxy
            url = f"{self.api_url}/core/api/config"
            response = requests.get(url, headers=self.get_headers(), timeout=5)
            if response.status_code == 200:
                tz = response.json().get("time_zone", fallback)
                if tz == "UTC":
                    tz = "Asia/Kolkata"
                logger.info(f"Discovered Home Assistant timezone: {tz}")
                return tz
        except Exception as e:
            logger.warning(f"Could not discover timezone from HA config: {e}")
        return fallback
