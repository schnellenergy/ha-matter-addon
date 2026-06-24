import asyncio
import signal
import sys
import json
import time
from typing import Dict, Any, Optional, Tuple

from startup import StartupCoordinator
from collectors.custom_storage_collector import CustomStorageCollector
from collectors.websocket_collector import HomeAssistantWebsocketCollector
from google.apps_script_client import GoogleAppsScriptClient
from google.sheet_writer import GoogleSheetWriter
from processors.filters import should_filter_event
from logger import logger

class DataCollectorApplication:
    """Main orchestrator for the Data Collector application."""
    
    def __init__(self):
        self.coordinator = StartupCoordinator()
        self.custom_storage_collector: Optional[CustomStorageCollector] = None
        self.gas_client: Optional[GoogleAppsScriptClient] = None
        self.sheet_writer: Optional[GoogleSheetWriter] = None
        self.ws_collector: Optional[HomeAssistantWebsocketCollector] = None
        
        # Processor pipelines
        self.parser = None
        self.enricher = None
        
        # Deduplication cache
        self.last_state_cache: Dict[str, Tuple[str, float]] = {}  # entity_id -> (state, timestamp)
        
        # Tasks reference
        self.tasks = []
        self.loop = None
        self._running = True

    async def initialize(self) -> bool:
        """Executes startup discovery and initializes internal components."""
        # 1. Run discovery
        await self.coordinator.run_discovery_flow()
        
        # 2. Instantiate processors
        self.parser, self.enricher = self.coordinator.create_processors()
        
        # 3. Instantiate Custom Storage Collector
        self.custom_storage_collector = CustomStorageCollector(
            base_url=self.coordinator.config_manager.custom_storage_url
        )
        
        # Perform initial metadata pull before starting websocket to ensure maps are loaded
        logger.info("[App] Performing initial Custom Storage metadata sync...")
        await self.custom_storage_collector.fetch_metadata()
        
        # 4. Instantiate Google Apps Script Client & Writer
        self.gas_client = GoogleAppsScriptClient(
            apps_script_url=self.coordinator.config_manager.apps_script_url,
            hub_id=self.coordinator.hub_id,
            batch_size=1,
            batch_window_seconds=0
        )
        self.sheet_writer = GoogleSheetWriter(client=self.gas_client)
        
        # 5. Instantiate WebSocket Collector
        self.ws_collector = HomeAssistantWebsocketCollector(
            ws_url=self.coordinator.ha_ws_url,
            token=self.coordinator.ha_token,
            enricher=self.enricher,
            event_callback=self.on_event_received
        )
        
        return True

    def on_event_received(self, raw_event: Dict[str, Any]):
        """Callback invoked when a new event is received from HA WebSocket."""
        try:
            event_type = raw_event.get("event_type", "unknown")
            event_data = raw_event.get("data", {})
            entity_id = event_data.get("entity_id")
            
            # 1. Evaluate filter rules
            if should_filter_event(event_type, entity_id):
                logger.debug(f"[App] Filtered out noisy event: {event_type} (entity: {entity_id})")
                return

            # Deduplicate state changes occurring within 500ms to avoid bounce transitions
            if event_type == "state_changed" and entity_id:
                new_state = event_data.get("new_state", {})
                new_val = new_state.get("state") if new_state else None
                if new_val:
                    curr_time = time.time()
                    if entity_id in self.last_state_cache:
                        last_val, last_time = self.last_state_cache[entity_id]
                        if last_val == new_val and (curr_time - last_time < 0.5):
                            logger.debug(f"[App] Deduplicated rapid repeat state change for {entity_id} to '{new_val}'")
                            return
                    self.last_state_cache[entity_id] = (new_val, curr_time)

            logger.debug(f"[App] Processing event: {event_type} (entity: {entity_id})")
            
            # 2. Parse raw event
            parsed = self.parser.parse_event(raw_event)
            
            # 3. Fetch Custom Storage metadata cache
            # Note: Since this callback runs synchronously in the WS receive thread/task,
            # we query the thread-safe synchronous cache getter of Custom Storage.
            # However, since get_metadata_cache is async, we can construct the enricher call
            # by fetching the cache synchronously or scheduling it. Let's make get_metadata_cache
            # return the data directly by avoiding async if possible, or scheduling the enrichment task!
            # Scheduling the enrichment task in the event loop is much cleaner and fully async.
            self.loop.create_task(self.process_and_enrich_async(parsed))

        except Exception as e:
            logger.error(f"[App] Error in on_event_received callback: {e}", exc_info=True)

    async def process_and_enrich_async(self, parsed_event: Dict[str, Any]):
        """Enriches the parsed event with Custom Storage metadata and pushes to sheet buffer."""
        try:
            # Get metadata from poller
            custom_metadata = await self.custom_storage_collector.get_metadata_cache()
            
            # Enrich
            enriched = self.enricher.enrich_event(parsed_event, custom_metadata)
            
            # Filter and map to the exact 29 columns requested by the user
            output_fields = [
                "timestamp", "date", "time", "hour", "day_of_week", "ha_event_type",
                "entity_id", "domain", "friendly_name", "old_state", "new_state",
                "brightness", "fan_speed", "color_name", "action", "origin",
                "attributes", "raw_event_json", "device_id", "log_source", "room",
                "floor", "device_type", "docklet_state_change_ts", "matter_command_ts",
                "snap_state_change_ts", "thread_node_id", "use_case"
            ]
            
            final_event = {"hub_id": self.coordinator.hub_id}
            final_event.update({field: enriched.get(field) for field in output_fields})
            
            # Write/Queue to Sheets buffer
            await self.sheet_writer.write_event(final_event)
            
        except Exception as e:
            logger.error(f"[App] Error in async event enrichment/writing: {e}", exc_info=True)

    async def start(self):
        """Starts all background tasks and waits for termination."""
        self.loop = asyncio.get_running_loop()
        
        # Register shutdown signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self.loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(s)))
            except NotImplementedError:
                # Signal handlers are not fully supported on some Windows platforms, fallback is ok
                pass

        logger.info("[App] Launching background sync operations...")
        
        # Start background tasks
        custom_storage_task = asyncio.create_task(
            self.custom_storage_collector.start_polling_loop(interval_seconds=30)
        )
        gas_timeout_task = asyncio.create_task(
            self.gas_client.start_timeout_monitor()
        )
        ws_listener_task = asyncio.create_task(
            self.ws_collector.connect_and_listen()
        )
        
        self.tasks = [custom_storage_task, gas_timeout_task, ws_listener_task]
        
        # Wait for all tasks
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def shutdown(self, sig=None):
        """Performs clean shutdown, stopping collectors and flushing remaining events."""
        if not self._running:
            return
        self._running = False
        
        if sig:
            logger.info(f"[App] Shutdown triggered by signal {sig.name}...")
        else:
            logger.info("[App] Shutdown triggered...")

        # 1. Stop collector loops
        if self.ws_collector:
            self.ws_collector.stop()
        if self.custom_storage_collector:
            # We don't have a stop on custom_storage but cancelling its task will cancel it
            pass
        if self.gas_client:
            self.gas_client.stop()

        # 2. Cancel all running background tasks
        logger.info("[App] Cancelling background loops...")
        for task in self.tasks:
            task.cancel()
            
        # 3. Flush any remaining events in the buffer
        if self.gas_client:
            logger.info("[App] Flushing remaining event buffer to Google Sheets before exiting...")
            await self.gas_client.flush()

        logger.info("[App] Cleanup completed. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    app = DataCollectorApplication()
    
    # Establish async loop
    async def main():
        success = await app.initialize()
        if not success:
            logger.critical("[App] Initialization failed. Exiting.")
            sys.exit(1)
        await app.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[App] Exited via keyboard interrupt")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"[App] Unhandled runtime exception: {e}", exc_info=True)
        sys.exit(1)
