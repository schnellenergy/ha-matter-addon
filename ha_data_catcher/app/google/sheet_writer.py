from typing import Dict, Any
from google.apps_script_client import GoogleAppsScriptClient
from logger import logger

class GoogleSheetWriter:
    """Abstraction layer representing the interface to write records to Google Sheets."""
    
    def __init__(self, client: GoogleAppsScriptClient):
        self.client = client
        logger.info("Google Sheets Writer interface initialized")

    async def write_event(self, event_data: Dict[str, Any]):
        """Queues an event record to be written to Google Sheets."""
        # Delegates directly to the underlying Apps Script client buffer
        await self.client.add_event(event_data)
