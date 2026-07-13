import asyncio
import os
from typing import Dict, Any, List, Optional
from logger import logger

import firebase_admin
from firebase_admin import credentials, firestore as fs_admin

_MAX_BATCH = 450  # Firestore batch write ceiling is 500 ops
_CREDENTIALS_PATH = "/firebase-service-account.json"

class FirestoreWriter:
    """
    Writes enriched HA events to Firestore under:
        smash_db/<hub_mac>/ha_events/<event_id>

    Mirrors the Flutter app's AppEventSink path so both sources live under
    the same hub document and the Firebase BigQuery extension picks them up
    via the 'ha_events' collection group.

    Credentials are baked into the container at build time from
    firebase-service-account.json in the addon folder.
    """

    def __init__(self, hub_mac: str):
        self._hub_mac = hub_mac
        self._db: Optional[Any] = None
        self._buffer: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._running = True
        self._init_firebase()

    def _init_firebase(self):
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred)
            self._db = fs_admin.client()
            logger.info(f"[Firestore] Initialized. Hub path: smash_db/{self._hub_mac}/ha_events")
        except Exception as e:
            logger.error(f"[Firestore] Failed to initialize Firebase Admin SDK: {e}", exc_info=True)
            self._db = None

    async def write_event(self, event: Dict[str, Any]):
        """Queues a single event. Flushes immediately (batch_size=1 to match current Sheets behaviour)."""
        if self._db is None:
            logger.warning("[Firestore] Client not initialized — event dropped.")
            return
        async with self._lock:
            self._buffer.append(event)
        asyncio.create_task(self._flush_if_ready())

    async def _flush_if_ready(self):
        async with self._lock:
            if not self._buffer:
                return
            batch_to_send = self._buffer.copy()
            self._buffer.clear()

        await self._write_batch(batch_to_send)

    async def _write_batch(self, events: List[Dict[str, Any]]):
        if self._db is None:
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._write_batch_sync, events)
            logger.info(f"[Firestore] Wrote {len(events)} ha_event(s) to Firestore.")
        except Exception as e:
            logger.error(f"[Firestore] Batch write failed: {e}", exc_info=True)

    def _write_batch_sync(self, events: List[Dict[str, Any]]):
        """Synchronous Firestore batch write, run in a thread executor."""
        hub_ref = self._db.collection("smash_db").document(self._hub_mac)
        for i in range(0, len(events), _MAX_BATCH):
            chunk = events[i:i + _MAX_BATCH]
            batch = self._db.batch()
            for event in chunk:
                event_id = event.get("event_id")
                if not event_id:
                    logger.warning("[Firestore] Event missing event_id — skipping.")
                    continue
                doc_ref = hub_ref.collection("ha_events").document(event_id)
                batch.set(doc_ref, event)
            batch.commit()

    async def flush(self):
        """Flush any remaining buffered events (called on shutdown)."""
        async with self._lock:
            if not self._buffer:
                return
            batch_to_send = self._buffer.copy()
            self._buffer.clear()
        await self._write_batch(batch_to_send)

    def stop(self):
        self._running = False
