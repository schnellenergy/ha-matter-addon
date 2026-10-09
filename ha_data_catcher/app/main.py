import asyncio
import signal
import sys
import time
from typing import Dict, Any, Optional, Tuple

from startup import StartupCoordinator
from collectors.custom_storage_collector import CustomStorageCollector
from collectors.websocket_collector import HomeAssistantWebsocketCollector
from collectors.matter_collector import MatterDockCollector, parse_endpoint_range
from firebase.firestore_writer import FirestoreWriter
from processors.dock_telemetry import DockTelemetryProcessor
from processors.filters import should_filter_event
from logger import logger

# Fields written to Firestore for every ha_event document.
# Mirrors the ha_logs.csv contract used in the analytics pipeline.
_OUTPUT_FIELDS = [
    "event_id",
    "timestamp", "date", "time", "hour", "day_of_week",
    "log_source", "actuation_source", "use_case", "ha_event_type",
    "entity_id", "domain", "friendly_name",
    "old_state", "new_state", "action", "origin",
    "context_id", "context_user_id",
    "trigger_id", "is_trigger",
    "room", "floor", "device_type",
    "docklet_id", "dock_id",
    "docklet_state_change_ts", "matter_command_ts", "snap_state_change_ts",
    "ha_processing_latency_ms",
    "thread_node_id",
    "network_type",
    "success", "failure_reason",
]


class DataCollectorApplication:
    """Main orchestrator for the Data Collector application."""

    def __init__(self):
        self.coordinator = StartupCoordinator()
        self.custom_storage_collector: Optional[CustomStorageCollector] = None
        self.firestore_writer: Optional[FirestoreWriter] = None
        self.ws_collector: Optional[HomeAssistantWebsocketCollector] = None

        # Dock telemetry (optional, gated by the enable_dock_telemetry option)
        self.matter_collector: Optional[MatterDockCollector] = None
        self.dock_processor: Optional[DockTelemetryProcessor] = None

        # Processor pipelines
        self.parser = None
        self.enricher = None

        # Deduplication cache: entity_id -> (state, timestamp)
        self.last_state_cache: Dict[str, Tuple[str, float]] = {}

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

        # Perform initial metadata pull before starting websocket
        logger.info("[App] Performing initial Custom Storage metadata sync...")
        await self.custom_storage_collector.fetch_metadata()

        # 4. Instantiate Firestore Writer
        self.firestore_writer = FirestoreWriter(
            hub_mac=self.coordinator.hub_id,
        )

        # 5. Instantiate WebSocket Collector
        self.ws_collector = HomeAssistantWebsocketCollector(
            ws_url=self.coordinator.ha_ws_url,
            token=self.coordinator.ha_token,
            enricher=self.enricher,
            event_callback=self.on_event_received
        )

        # 6. Instantiate dock telemetry (optional feature)
        self._init_dock_telemetry()

        return True

    def _init_dock_telemetry(self):
        """Sets up Matter dock counter collection, if enabled.

        Isolated and fully non-fatal: any failure here leaves the Home
        Assistant event pipeline running exactly as before.
        """
        config = self.coordinator.config_manager
        if not config.enable_dock_telemetry:
            logger.info("[App] Dock telemetry disabled by configuration — skipping Matter Server collector")
            return

        try:
            self.dock_processor = DockTelemetryProcessor(
                hub_id=self.coordinator.hub_id,
                timezone_name=self.coordinator.ha_timezone,
                metadata_provider=self.custom_storage_collector.get_metadata_cache,
                record_writer=self.firestore_writer.write_dock_record,
                debounce_seconds=config.dock_min_write_interval,
                # Shared read-only so a dock whose matter_node_id the app failed
                # to save can still be identified via HA's device registry.
                enricher=self.enricher,
            )
            self.matter_collector = MatterDockCollector(
                ws_url=config.matter_server_url,
                snapshot_callback=self.dock_processor.handle_snapshot,
                product_name_prefixes=config.dock_product_names,
                cluster_id=config.dock_cluster_id,
                endpoints=parse_endpoint_range(config.dock_endpoints),
                poll_interval=config.dock_poll_interval,
            )
            logger.info(
                "[App] Dock telemetry enabled — products "
                f"{config.dock_product_names}, cluster {config.dock_cluster_id}, "
                f"endpoints {config.dock_endpoints}"
            )
        except Exception as e:
            logger.error(
                f"[App] Failed to initialize dock telemetry: {e}. "
                "Home Assistant event collection continues unaffected.",
                exc_info=True,
            )
            self.matter_collector = None
            self.dock_processor = None

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

            # Deduplicate state changes within 500ms to avoid bounce transitions
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

            # Schedule async enrichment + write
            self.loop.create_task(self.process_and_write_async(parsed))

        except Exception as e:
            logger.error(f"[App] Error in on_event_received callback: {e}", exc_info=True)

    async def process_and_write_async(self, parsed_event: Dict[str, Any]):
        """Enriches the parsed event and writes it to Firestore as an ha_event."""
        try:
            # Get metadata from Custom Storage poller
            custom_metadata = await self.custom_storage_collector.get_metadata_cache()

            # Pick up the app's self-reported HA user id as soon as it's
            # available — no restart needed, no config to type. See
            # CustomStorageCollector._parse_app_identity.
            reported_id = custom_metadata.get("app_ha_user_id")
            if reported_id and self.enricher.app_ha_user_id != reported_id:
                self.enricher.app_ha_user_id = reported_id

            # Enrich with Custom Storage + HA registry data
            enriched = self.enricher.enrich_event(parsed_event, custom_metadata)

            # Build the Firestore document from the canonical output fields
            doc = {"hub_id": self.coordinator.hub_id}
            doc.update({field: enriched.get(field) for field in _OUTPUT_FIELDS})

            # Remove None values so Firestore doesn't store explicit nulls for
            # optional fields — keeps documents lean and matches app_events style.
            doc = {k: v for k, v in doc.items() if v is not None}

            await self.firestore_writer.write_event(doc)

        except Exception as e:
            logger.error(f"[App] Error in async event enrichment/writing: {e}", exc_info=True)

    async def start(self):
        """Starts all background tasks and waits for termination."""
        self.loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self.loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(s)))
            except NotImplementedError:
                pass

        logger.info("[App] Launching background sync operations...")

        custom_storage_task = asyncio.create_task(
            self.custom_storage_collector.start_polling_loop(interval_seconds=30)
        )
        ws_listener_task = asyncio.create_task(
            self.ws_collector.connect_and_listen()
        )

        self.tasks = [custom_storage_task, ws_listener_task]

        # Dock telemetry runs as two additional independent tasks. gather() with
        # return_exceptions=True means a failure in either cannot take down the
        # Home Assistant event pipeline.
        if self.matter_collector and self.dock_processor:
            self.tasks.append(asyncio.create_task(self.dock_processor.run()))
            self.tasks.append(asyncio.create_task(self.matter_collector.run()))

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

        if self.ws_collector:
            self.ws_collector.stop()
        if self.matter_collector:
            self.matter_collector.stop()

        if self.dock_processor:
            self.dock_processor.stop()
            logger.info("[App] Flushing pending dock counter updates...")
            try:
                await self.dock_processor.flush()
            except Exception as e:
                logger.error(f"[App] Error flushing dock telemetry: {e}")

        logger.info("[App] Cancelling background loops...")
        for task in self.tasks:
            task.cancel()

        if self.firestore_writer:
            logger.info("[App] Flushing remaining Firestore event buffer before exiting...")
            await self.firestore_writer.flush()

        logger.info("[App] Cleanup completed. Exiting.")
        sys.exit(0)


if __name__ == "__main__":
    app = DataCollectorApplication()

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
