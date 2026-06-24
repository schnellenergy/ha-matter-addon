import asyncio
import json
import time
import aiohttp
from typing import List, Dict, Any
from logger import logger

class GoogleAppsScriptClient:
    """Handles batched upload of events to Google Apps Script Webhook with retries."""
    
    def __init__(
        self,
        apps_script_url: str,
        hub_id: str,
        batch_size: int = 100,
        batch_window_seconds: int = 30,
        max_retries: int = 3
    ):
        self.apps_script_url = apps_script_url
        self.hub_id = hub_id
        self.batch_size = batch_size
        self.batch_window_seconds = batch_window_seconds
        self.max_retries = max_retries
        
        # Event buffer
        self.buffer: List[Dict[str, Any]] = []
        self.last_flush_time = time.time()
        self.lock = asyncio.Lock()
        self._running = True

    async def add_event(self, event: Dict[str, Any]):
        """Adds a single event to the buffer. Flushes if batch size reached."""
        async with self.lock:
            self.buffer.append(event)
            buffer_len = len(self.buffer)
            
        logger.debug(f"Event added to buffer. Buffer size: {buffer_len}/{self.batch_size}")
        if buffer_len >= self.batch_size:
            logger.info(f"Buffer batch size ({self.batch_size}) reached. Triggering flush.")
            # Trigger flush in a background task so it doesn't block the caller
            asyncio.create_task(self.flush())

    async def flush(self):
        """Flushes the event buffer and uploads batched events to Apps Script."""
        async with self.lock:
            if not self.buffer:
                self.last_flush_time = time.time()
                return
            
            # Copy buffer content and clear the buffer
            batch_to_send = self.buffer.copy()
            self.buffer.clear()
            self.last_flush_time = time.time()

        if not self.apps_script_url:
            logger.warning(f"Google Apps Script URL is not configured. Discarding batch of {len(batch_to_send)} events.")
            return

        logger.info(f"Uploading batch of {len(batch_to_send)} events to Google Sheets...")
        
        payload = {
            "hub_id": self.hub_id,
            "events": batch_to_send
        }
        
        # Perform upload with retries
        success = await self._upload_with_retry(payload)
        
        # If upload failed, restore events back to the buffer to avoid data loss
        if not success:
            logger.error(f"Failed to upload batch of {len(batch_to_send)} events. Restoring events to buffer for retry.")
            async with self.lock:
                # Put failed events back at the front of the buffer
                self.buffer = batch_to_send + self.buffer
                # Limit buffer size to avoid memory overflow (e.g. max 5000 events)
                if len(self.buffer) > 5000:
                    dropped_count = len(self.buffer) - 5000
                    self.buffer = self.buffer[:5000]
                    logger.warning(f"Buffer limit exceeded. Dropped {dropped_count} oldest events to prevent memory overflow.")

    async def _upload_with_retry(self, payload: Dict[str, Any]) -> bool:
        """Sends payload to Google Sheets Webhook, performing retries on failures."""
        headers = {"Content-Type": "application/json"}
        
        for attempt in range(1, self.max_retries + 1):
            try:
                # Use client session with clean headers
                async with aiohttp.ClientSession() as session:
                    # Set a robust timeout (e.g. 30 seconds, GAS execution can sometimes be slow)
                    timeout = aiohttp.ClientTimeout(total=30)
                    
                    async with session.post(
                        self.apps_script_url,
                        json=payload,
                        headers=headers,
                        timeout=timeout
                    ) as response:
                        
                        if response.status == 200:
                            body = await response.json()
                            if body.get("status") == "success" or body.get("success") is True:
                                logger.info(f"Successfully uploaded batch of {payload.get('events', []) and len(payload['events'])} events.")
                                return True
                            else:
                                logger.error(f"Google Apps Script returned business error: {body}")
                        else:
                            resp_text = await response.text()
                            logger.error(f"Google Apps Script HTTP {response.status} Error: {resp_text}")
                            
            except aiohttp.ClientError as e:
                logger.warning(f"Network error on upload attempt {attempt}/{self.max_retries}: {e}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on upload attempt {attempt}/{self.max_retries}")
            except Exception as e:
                logger.error(f"Unexpected upload error on attempt {attempt}/{self.max_retries}: {e}")
                
            if attempt < self.max_retries:
                backoff_time = 2 ** attempt
                logger.info(f"Retrying upload in {backoff_time} seconds...")
                await asyncio.sleep(backoff_time)
                
        return False

    async def start_timeout_monitor(self):
        """Monitors buffer age and flushes if the time since last flush exceeds window."""
        logger.info(f"Starting Google Sheets buffer timeout monitor (window: {self.batch_window_seconds}s)")
        while self._running:
            try:
                current_time = time.time()
                # Check if buffer has items and last flush exceeds batch window
                async with self.lock:
                    has_items = len(self.buffer) > 0
                    time_passed = current_time - self.last_flush_time
                    
                if has_items and time_passed >= self.batch_window_seconds:
                    logger.info(f"Batch window ({self.batch_window_seconds}s) expired. Flushing {len(self.buffer)} events.")
                    # Flush is run directly (we are not blocking other operations)
                    await self.flush()
            except Exception as e:
                logger.error(f"Error in timeout monitor loop: {e}")
                
            await asyncio.sleep(1)

    def stop(self):
        self._running = False
