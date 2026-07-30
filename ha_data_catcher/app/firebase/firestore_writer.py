import asyncio
import os
from typing import Dict, Any, List, Optional
from logger import logger

import firebase_admin
from firebase_admin import credentials, firestore as fs_admin

_MAX_BATCH = 450  # Firestore batch write ceiling is 500 ops
_CREDENTIALS_PATH = "/firebase-service-account.json"

# Collection names under the hub document, and the field each one uses as its
# document id. Both are picked up by the Firebase BigQuery extension as
# separate collection groups.
_EVENTS_COLLECTION = "ha_events"
_EVENTS_ID_FIELD = "event_id"
_DOCK_COLLECTION = "dock_events"
_DOCK_ID_FIELD = "record_id"


class FirestoreWriter:
    """
    Writes enriched telemetry to Firestore under:
        smash_db/<hub_mac>/ha_events/<event_id>       — Home Assistant events
        smash_db/<hub_mac>/dock_events/<record_id>    — dock hardware counters

    Mirrors the Flutter app's AppEventSink path so every source lives under the
    same hub document and the Firebase BigQuery extension picks them up via
    collection groups.

    Credentials are baked into the container at build time from
    firebase-service-account.json in the addon folder.
    """

    def __init__(self, hub_mac: str):
        self._hub_mac = hub_mac
        self._db: Optional[Any] = None
        self._buffer: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        # Dock records are buffered separately: they use a different collection
        # and a different document-id field, and a stall on one stream must not
        # hold up the other.
        self._dock_buffer: List[Dict[str, Any]] = []
        self._dock_lock = asyncio.Lock()
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

    # ------------------------------------------------------------------ #
    # Home Assistant events
    # ------------------------------------------------------------------ #

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
            await loop.run_in_executor(
                None, self._write_collection_sync,
                _EVENTS_COLLECTION, _EVENTS_ID_FIELD, events,
            )
            logger.info(f"[Firestore] Wrote {len(events)} ha_event(s) to Firestore.")
        except Exception as e:
            logger.error(f"[Firestore] Batch write failed: {e}", exc_info=True)

    # ------------------------------------------------------------------ #
    # Dock hardware counters
    # ------------------------------------------------------------------ #

    async def write_dock_record(self, record: Dict[str, Any]):
        """Queues a single dock counter record and flushes it immediately."""
        if self._db is None:
            logger.warning("[Firestore] Client not initialized — dock record dropped.")
            return
        async with self._dock_lock:
            self._dock_buffer.append(record)
        await self._flush_dock_if_ready()

    async def _flush_dock_if_ready(self):
        async with self._dock_lock:
            if not self._dock_buffer:
                return
            batch_to_send = self._dock_buffer.copy()
            self._dock_buffer.clear()

        await self._write_dock_batch(batch_to_send)

    async def _write_dock_batch(self, records: List[Dict[str, Any]]):
        if self._db is None:
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, self._write_collection_sync,
                _DOCK_COLLECTION, _DOCK_ID_FIELD, records,
            )
            logger.info(f"[Firestore] Wrote {len(records)} dock record(s) to Firestore.")
        except Exception as e:
            logger.error(f"[Firestore] Dock batch write failed: {e}", exc_info=True)
            raise

    # ------------------------------------------------------------------ #
    # Shared batch machinery
    # ------------------------------------------------------------------ #

    def _write_collection_sync(self, collection: str, id_field: str, docs: List[Dict[str, Any]]):
        """Synchronous Firestore batch write, run in a thread executor."""
        if self._db is None:
            return
        hub_ref = self._db.collection("smash_db").document(self._hub_mac)
        for i in range(0, len(docs), _MAX_BATCH):
            chunk = docs[i:i + _MAX_BATCH]
            batch = self._db.batch()
            for doc in chunk:
                doc_id = doc.get(id_field)
                if not doc_id:
                    logger.warning(f"[Firestore] Document missing {id_field} — skipping.")
                    continue
                doc_ref = hub_ref.collection(collection).document(str(doc_id))
                batch.set(doc_ref, doc)
            batch.commit()

    async def flush(self):
        """Flush any remaining buffered records (called on shutdown)."""
        async with self._lock:
            batch_to_send = self._buffer.copy()
            self._buffer.clear()
        if batch_to_send:
            await self._write_batch(batch_to_send)

        async with self._dock_lock:
            dock_batch = self._dock_buffer.copy()
            self._dock_buffer.clear()
        if dock_batch:
            try:
                await self._write_dock_batch(dock_batch)
            except Exception:
                pass  # already logged; shutdown must not be blocked by a failed flush

    def stop(self):
        self._running = False
