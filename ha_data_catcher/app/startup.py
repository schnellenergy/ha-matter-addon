import asyncio
from config_manager import ConfigManager
from supervisor import SupervisorClient
from collectors.custom_storage_collector import CustomStorageCollector
from processors.event_enricher import EventEnricher
from processors.event_parser import EventParser
from logger import logger, setup_logger

class StartupCoordinator:
    """Orchestrates the discovery and initialization sequence on add-on startup."""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.supervisor_client = SupervisorClient()
        
        # Discovered parameters
        self.ha_ip = "homeassistant"
        self.ha_port = 8123
        self.ha_ws_url = "ws://homeassistant:8123/api/websocket"
        self.ha_token = ""
        self.ha_timezone = "Asia/Kolkata"
        self.hub_id = "HUB_UNKNOWN"

    async def run_discovery_flow(self) -> bool:
        """Executes the startup configuration and auto-discovery steps."""
        logger.info("==================================================")
        logger.info("[Startup] Initiating discovery sequence...")
        
        # 1. Re-configure debug logs if requested
        if self.config_manager.debug:
            setup_logger("data_collector", debug_mode=True)
            logger.debug("[Startup] Debug logging enabled")

        # 2. Query Supervisor for Core details
        ha_details = self.supervisor_client.get_ha_details(self.config_manager.ha_token)
        self.ha_ip = ha_details["ha_ip"]
        self.ha_port = ha_details["ha_port"]
        self.ha_ws_url = ha_details["ws_url"]
        self.ha_token = ha_details["token"]
        
        logger.info(f"[Startup] Home Assistant Core IP: {self.ha_ip}")
        logger.info(f"[Startup] Home Assistant Core Port: {self.ha_port}")
        logger.info(f"[Startup] Home Assistant WebSocket: {self.ha_ws_url}")
        logger.info(f"[Startup] Home Assistant Auth Token: {'Provided' if self.ha_token else 'Not Found (Check Settings)'}")
        
        # 3. Determine Hub ID
        if self.config_manager.hub_id:
            self.hub_id = self.config_manager.hub_id
            logger.info(f"[Startup] Hub ID (Explicitly Configured): {self.hub_id}")
        else:
            logger.info("[Startup] Hub ID not configured. Querying auto-discovery...")
            self.hub_id = self.supervisor_client.discover_hub_id(self.config_manager.custom_storage_url)
            logger.info(f"[Startup] Hub ID (Auto-Discovered): {self.hub_id}")
            
        # 4. Determine Timezone
        self.ha_timezone = self.supervisor_client.get_ha_timezone()
        logger.info(f"[Startup] Timezone: {self.ha_timezone}")
        
        logger.info("[Startup] Discovery sequence complete.")
        logger.info("==================================================")
        return True

    def create_processors(self) -> tuple[EventParser, EventEnricher]:
        """Creates event parser and enricher objects based on discovered configs."""
        tz_name = self.ha_timezone
        if tz_name in ("UTC", "Etc/UTC") or not tz_name:
            tz_name = "Asia/Kolkata"
        parser = EventParser(timezone_name=tz_name)
        enricher = EventEnricher()
        return parser, enricher
