import asyncio
import json
import aiohttp
from typing import Dict, Any, Optional
from logger import logger

class CustomStorageCollector:
    """Fetches and caches metadata maps from the Custom Data Storage API."""
    
    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        
        # Internal caches
        self.rooms: Dict[str, Dict[str, Any]] = {}
        self.snaps: Dict[str, Dict[str, Any]] = {}
        self.docks: Dict[str, Dict[str, Any]] = {}
        
        # Thread/Async lock
        self.lock = asyncio.Lock()
        
    def get_headers(self) -> Dict[str, str]:
        """Generate headers, adding X-API-Key if configured."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def fetch_metadata(self) -> bool:
        """Queries Custom Storage API endpoints and refreshes local maps."""
        success = True
        
        async with aiohttp.ClientSession() as session:
            # 1. Fetch Home Setup (Floors and Rooms)
            home_url = f"{self.base_url}/api/data/home_setup"
            try:
                async with session.get(home_url, headers=self.get_headers(), timeout=10) as resp:
                    if resp.status == 200:
                        body = await resp.json()
                        if body.get("success"):
                            val = body.get("value") or body.get("data")
                            if val is None:
                                logger.warning(f"Custom Storage API response has success=True but missing both 'value' and 'data' fields: {body}")
                                success = False
                            else:
                                if isinstance(val, str):
                                    val = json.loads(val)
                                if isinstance(val, dict):
                                    await self._parse_home_setup(val)
                                logger.debug("Successfully updated rooms/floors cache from Custom Storage")
                        else:
                            logger.warning(f"Custom Storage API reported error: {body}")
                            success = False
                    else:
                        logger.warning(f"Could not reach {home_url}, status: {resp.status}")
                        success = False
            except Exception as e:
                logger.warning(f"Error connecting to Custom Storage home_setup: {e}")
                success = False

            # 2. Fetch Device Setup (Snaps and Docks)
            device_url = f"{self.base_url}/api/data/device_setup"
            try:
                async with session.get(device_url, headers=self.get_headers(), timeout=10) as resp:
                    if resp.status == 200:
                        body = await resp.json()
                        if body.get("success"):
                            val = body.get("value") or body.get("data")
                            if val is None:
                                logger.warning(f"Custom Storage API response has success=True but missing both 'value' and 'data' fields: {body}")
                                success = False
                            else:
                                if isinstance(val, str):
                                    val = json.loads(val)
                                if isinstance(val, dict):
                                    await self._parse_device_setup(val)
                                logger.debug("Successfully updated snaps/docks cache from Custom Storage")
                        else:
                            logger.warning(f"Custom Storage API reported error: {body}")
                            success = False
                    else:
                        logger.warning(f"Could not reach {device_url}, status: {resp.status}")
                        success = False
            except Exception as e:
                logger.warning(f"Error connecting to Custom Storage device_setup: {e}")
                success = False
                
        return success

    async def _parse_home_setup(self, home_setup: Dict[str, Any]):
        """Parses the home structure to populate room and floor mappings."""
        new_rooms = {}
        setup_data = home_setup.get("structure", home_setup) if isinstance(home_setup.get("structure"), dict) else home_setup
        floors = setup_data.get("floors", [])
        for floor in floors:
            floor_name = floor.get("name", "Unknown Floor")
            rooms = floor.get("rooms", [])
            for room in rooms:
                room_id = room.get("room_id")
                if room_id:
                    new_rooms[room_id] = {
                        "name": room.get("name", "Unknown Room"),
                        "floor_name": floor_name
                    }
                    
        async with self.lock:
            self.rooms = new_rooms
            logger.info(f"Successfully loaded {len(self.rooms)} rooms from Custom Storage metadata")
            
    async def _parse_device_setup(self, device_setup: Dict[str, Any]):
        """Parses device setup for snaps and docks maps."""
        async with self.lock:
            setup_data = device_setup.get("structure", device_setup) if isinstance(device_setup.get("structure"), dict) else device_setup
            self.snaps = setup_data.get("snaps", {})
            self.docks = setup_data.get("docks", {})
            logger.info(f"Successfully loaded {len(self.snaps)} snaps and {len(self.docks)} docks from Custom Storage metadata")

    async def start_polling_loop(self, interval_seconds: int = 30):
        """Runs an infinite polling loop in a background task."""
        logger.info(f"Starting Custom Storage polling background loop (interval: {interval_seconds}s)")
        while True:
            try:
                await self.fetch_metadata()
            except Exception as e:
                logger.error(f"Unexpected error in Custom Storage poller: {e}")
            await asyncio.sleep(interval_seconds)

    async def get_metadata_cache(self) -> Dict[str, Any]:
        """Thread-safe access to current metadata cache."""
        async with self.lock:
            return {
                "rooms": self.rooms.copy(),
                "snaps": self.snaps.copy(),
                "docks": self.docks.copy()
            }
