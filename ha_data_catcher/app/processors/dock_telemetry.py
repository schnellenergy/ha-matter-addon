"""Turns raw dock counter snapshots into analytics rows.

The dock firmware exposes **cumulative** counters — totals since the device
booted, not per-press events. Three consequences drive everything in this
module:

1. A raw cumulative series cannot be ``SUM()``-ed for "presses today", so every
   row also carries the **delta** since the previous observation. Deltas are
   what make the BigQuery table aggregate the way the old Sheet-based table did.
2. A dock power-cycle restarts the counters at zero, which naively looks like a
   large negative jump. That is detected and flagged rather than emitted as a
   nonsense delta.
3. Deltas must survive an add-on restart, so last-seen counters are persisted
   to ``/data`` instead of living only in memory.

One row is emitted per **dock x endpoint x change**. An idle dock produces
nothing at all.
"""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from logger import logger

# Attribute id -> (cumulative field, delta field) on the output row.
COUNTER_FIELDS: Dict[int, Tuple[str, str]] = {
    2: ("press_total_count", "press_total_delta"),
    3: ("press_success_count", "press_success_delta"),
    4: ("encoder_total_count", "encoder_total_delta"),
    5: ("encoder_success_count", "encoder_success_delta"),
}

_STATE_VERSION = 1
_FLUSH_TICK = 0.5  # how often the debounce loop looks for ripe entries
_NOT_MAPPED = "not_mapped"

_NUMERIC_SUFFIX_RE = re.compile(r"(\d+)\s*$")

# Custom Data Storage is a schema-less key-value store: it persists whatever the
# mobile app writes, and the shape has varied between app versions (snake_case
# vs camelCase, docklets as a map vs a list, position under several names). The
# key lists below let identity resolution work across all of those rather than
# silently returning blank dock names when one field is spelled differently.
_NODE_ID_KEYS = (
    "matter_node_id", "matterNodeId", "matter_node", "matterNode",
    "node_id", "nodeId",
)
_LABEL_KEYS = ("label", "name", "dock_name", "dockName", "title", "display_name")
_DOCKLET_CONTAINER_KEYS = (
    "docklets", "sub_devices", "subDevices", "buttons", "slots", "endpoints",
)
_POSITION_KEYS = (
    "position", "endpoint_id", "endpointId", "endpoint",
    "index", "slot", "slot_number", "button", "docklet_position",
)
_DOCKLET_LABEL_KEYS = (
    "bound_device_label", "boundDeviceLabel", "label", "name",
    "docklet_label", "dockletLabel", "title",
)
_DOCKLET_ID_KEYS = (
    "entity_id", "entityId", "bound_device_entity_id", "boundDeviceEntityId",
    "docklet_id", "dockletId",
)
_ROOM_ID_KEYS = ("room_id", "roomId")


def _first(entry: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[str]:
    """First usable value among ``keys``, skipping blanks and placeholders."""
    for key in keys:
        if key in entry:
            value = _clean(entry[key])
            if value:
                return value
    return None


def _entry_node_id(entry: Dict[str, Any]) -> Optional[Any]:
    """The Matter node id a Custom Storage entry claims, whatever it is called."""
    for key in _NODE_ID_KEYS:
        if key in entry and entry[key] not in (None, ""):
            return entry[key]
    return None


def _device_matches_node(entry: Dict[str, Any], node_id: int) -> bool:
    """Whether a Custom Storage device entry refers to this Matter node."""
    if match_node_id(node_id, _entry_node_id(entry)):
        return True
    # Older app builds stored the node as an entity-style id instead.
    for key in ("entity_id", "entityId"):
        value = _clean(entry.get(key))
        if value and value.lower() in (f"node_{node_id}", f"matter_node_{node_id}"):
            return True
    return False


def _iter_docklets(entry: Dict[str, Any]):
    """Yields ``(key, docklet, implicit_position)`` for whichever shape is used.

    Handles both a keyed map (``{"docklet_1": {...}}``) and a plain list, under
    any of the container names the app has used.
    """
    for container_key in _DOCKLET_CONTAINER_KEYS:
        container = entry.get(container_key)
        if isinstance(container, dict):
            for key, docklet in container.items():
                if isinstance(docklet, dict):
                    yield str(key), docklet, None
            return
        if isinstance(container, list):
            for index, docklet in enumerate(container):
                if isinstance(docklet, dict):
                    yield str(docklet.get("id") or index + 1), docklet, index + 1
            return


def _docklet_position(key: str, docklet: Dict[str, Any],
                      implicit: Optional[int]) -> Optional[int]:
    """The endpoint this docklet sits on, however the app recorded it."""
    for position_key in _POSITION_KEYS:
        if position_key in docklet:
            try:
                return int(str(docklet[position_key]).strip())
            except (TypeError, ValueError):
                continue
    # Then list order, if this came from a list — an implicit position is more
    # trustworthy than a number parsed out of a synthesized key.
    if implicit is not None:
        return implicit
    # Finally the numeric suffix of the key ("docklet_1" -> 1).
    suffix = _NUMERIC_SUFFIX_RE.search(str(key))
    if suffix:
        return int(suffix.group(1))
    return None


def match_node_id(matter_node_id: Any, custom_node_id: Any) -> bool:
    """Matches a Matter node id against Custom Storage's stored value.

    Mirrors ``EventEnricher._match_matter_node_id`` so dock telemetry resolves
    identity exactly the way the ``ha_logs`` pipeline already does: exact match
    first, then numeric suffix (Custom Storage may hold "node_20", HA may hold
    "1-20", the Matter Server holds 20).
    """
    if matter_node_id is None or custom_node_id is None:
        return False

    left = str(matter_node_id).strip().lower()
    right = str(custom_node_id).strip().lower()
    if not left or not right:
        return False
    if left == right:
        return True

    left_match = _NUMERIC_SUFFIX_RE.search(left)
    right_match = _NUMERIC_SUFFIX_RE.search(right)
    if left_match and right_match:
        return left_match.group(1) == right_match.group(1)
    return False


def _clean(value: Any) -> Optional[str]:
    """Normalises a Custom Storage label, discarding placeholders."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == _NOT_MAPPED:
        return None
    return text


class DockTelemetryProcessor:
    """Debounces snapshots, computes deltas, resolves identity, emits rows."""

    def __init__(
        self,
        hub_id: str,
        timezone_name: str,
        metadata_provider: Callable[[], Awaitable[Dict[str, Any]]],
        record_writer: Callable[[Dict[str, Any]], Awaitable[None]],
        state_path: str = "/data/dock_counters.json",
        debounce_seconds: float = 2.0,
        enricher: Optional[Any] = None,
    ):
        self.hub_id = hub_id
        self.metadata_provider = metadata_provider
        self.record_writer = record_writer
        self.state_path = state_path
        self.debounce_seconds = max(0.0, float(debounce_seconds))
        # EventEnricher, reused read-only for its Home Assistant device registry.
        # Lets a dock whose matter_node_id the app failed to save still be
        # identified, via the docklet entities HA does know about.
        self.enricher = enricher

        try:
            self.tz = ZoneInfo(timezone_name)
        except Exception:
            logger.warning(f"[Dock] Unknown timezone '{timezone_name}' — falling back to Asia/Kolkata")
            self.tz = ZoneInfo("Asia/Kolkata")

        # Persisted last-seen cumulative counters:
        #   {node_id: {endpoint: {attribute_id: value}}}
        self._counters: Dict[int, Dict[int, Dict[int, int]]] = {}

        # Debounce buffer: (node_id, endpoint) -> merged pending snapshot.
        # A single press bumps attributes 2 and 3 within milliseconds; merging
        # them means one row per press instead of two half-filled rows.
        self._pending: Dict[Tuple[int, int], Dict[str, Any]] = {}

        self._running = True
        self._rows_written = 0
        self._rows_skipped = 0

        # Diagnostics are logged once, not once per row.
        self._unmatched_warned: set = set()
        self._docklet_warned: set = set()
        self._warned_tokens: set = set()

        # Distinct Matter nodes this processor has observed, used to decide
        # whether a sole-dock pairing is unambiguous.
        self._seen_nodes: set = set()

        self._load_state()

    # ------------------------------------------------------------------ #
    # Persisted counter state
    # ------------------------------------------------------------------ #

    def _load_state(self):
        if not os.path.exists(self.state_path):
            logger.info("[Dock] No saved counter state — first observation of each counter will be a baseline row")
            return
        try:
            with open(self.state_path, "r") as handle:
                payload = json.load(handle)
            counters = payload.get("counters", {}) if isinstance(payload, dict) else {}
            restored: Dict[int, Dict[int, Dict[int, int]]] = {}
            for node_id, endpoints in counters.items():
                for endpoint, attributes in (endpoints or {}).items():
                    for attribute, value in (attributes or {}).items():
                        restored.setdefault(int(node_id), {}) \
                                .setdefault(int(endpoint), {})[int(attribute)] = int(value)
            self._counters = restored
            total = sum(len(a) for eps in restored.values() for a in eps.values())
            logger.info(
                f"[Dock] Restored counter state for {len(restored)} node(s), "
                f"{total} counter(s) from {self.state_path}"
            )
        except Exception as e:
            logger.warning(
                f"[Dock] Could not read counter state at {self.state_path}: {e}. "
                "Continuing with an empty state (next rows will be baselines)."
            )
            self._counters = {}

    def _save_state(self):
        """Atomic write, so a crash mid-save cannot corrupt the state file."""
        payload = {
            "version": _STATE_VERSION,
            "hub_id": self.hub_id,
            "counters": {
                str(node_id): {
                    str(endpoint): {str(attr): value for attr, value in attributes.items()}
                    for endpoint, attributes in endpoints.items()
                }
                for node_id, endpoints in self._counters.items()
            },
        }
        temp_path = f"{self.state_path}.tmp"
        try:
            os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
            with open(temp_path, "w") as handle:
                json.dump(payload, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.state_path)
        except Exception as e:
            logger.warning(f"[Dock] Could not persist counter state: {e}")
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------ #
    # Snapshot intake (called synchronously by the Matter collector)
    # ------------------------------------------------------------------ #

    def handle_snapshot(self, snapshot: Dict[str, Any]):
        """Merges one raw snapshot into the debounce buffer."""
        try:
            node_id = int(snapshot["node_id"])
            endpoint = int(snapshot["endpoint"])
        except (KeyError, TypeError, ValueError):
            logger.warning(f"[Dock] Discarding malformed snapshot: {snapshot!r}")
            return

        counters = snapshot.get("counters") or {}
        if not counters:
            return

        self._seen_nodes.add(node_id)
        key = (node_id, endpoint)
        entry = self._pending.get(key)
        if entry is None:
            entry = {
                "node_id": node_id,
                "endpoint": endpoint,
                "product_name": snapshot.get("product_name") or "",
                "vendor_name": snapshot.get("vendor_name") or "",
                "cluster_id": snapshot.get("cluster_id"),
                "counters": {},
                "source": snapshot.get("source") or "push",
            }
            self._pending[key] = entry

        for attribute, value in counters.items():
            try:
                entry["counters"][int(attribute)] = int(value)
            except (TypeError, ValueError):
                continue

        # A live read is more authoritative than a reported update, so let a
        # poll relabel the merged entry, but never let push downgrade a poll.
        if snapshot.get("source") == "poll":
            entry["source"] = "poll"
        if snapshot.get("cluster_id") is not None:
            entry["cluster_id"] = snapshot.get("cluster_id")
        if snapshot.get("product_name"):
            entry["product_name"] = snapshot["product_name"]

        entry["last_update"] = time.monotonic()

    # ------------------------------------------------------------------ #
    # Debounce / flush loop
    # ------------------------------------------------------------------ #

    async def run(self):
        """Flushes debounced entries once they have settled."""
        logger.info(
            f"[Dock] Telemetry processor running — debounce {self.debounce_seconds}s, "
            f"state file {self.state_path}"
        )
        while self._running:
            try:
                await asyncio.sleep(_FLUSH_TICK)
                await self._flush_ripe()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[Dock] Flush loop error: {e}", exc_info=True)

    async def _flush_ripe(self):
        if not self._pending:
            return
        now = time.monotonic()
        ripe = [
            key for key, entry in self._pending.items()
            if now - entry.get("last_update", 0) >= self.debounce_seconds
        ]
        for key in ripe:
            entry = self._pending.pop(key, None)
            if entry:
                await self._process_entry(entry)

    async def flush(self):
        """Flushes everything pending, ignoring the debounce window."""
        if not self._pending:
            return
        logger.info(f"[Dock] Flushing {len(self._pending)} pending counter update(s)...")
        for key in list(self._pending):
            entry = self._pending.pop(key, None)
            if entry:
                await self._process_entry(entry)

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------ #
    # Delta computation and row building
    # ------------------------------------------------------------------ #

    async def _process_entry(self, entry: Dict[str, Any]):
        node_id = entry["node_id"]
        endpoint = entry["endpoint"]
        observed: Dict[int, int] = entry["counters"]

        previous = self._counters.get(node_id, {}).get(endpoint)
        is_baseline = previous is None
        previous = previous or {}

        cumulative: Dict[int, int] = {}
        deltas: Dict[int, int] = {}
        counter_reset = False
        changed = False

        for attribute in COUNTER_FIELDS:
            new_value = observed.get(attribute)
            old_value = previous.get(attribute)

            if new_value is None:
                # Not part of this update — carry the last known total forward
                # so the row still states all four absolute values.
                cumulative[attribute] = old_value if old_value is not None else 0
                deltas[attribute] = 0
                continue

            cumulative[attribute] = new_value

            if old_value is None:
                # First sighting of this counter: record the absolute value
                # without inventing history for it.
                deltas[attribute] = 0
                changed = True
            elif new_value > old_value:
                deltas[attribute] = new_value - old_value
                changed = True
            elif new_value < old_value:
                # Counters only ever climb, so a drop means the dock rebooted.
                counter_reset = True
                deltas[attribute] = new_value
                changed = True
            else:
                deltas[attribute] = 0

        if not changed and not is_baseline:
            self._rows_skipped += 1
            logger.debug(f"[Dock] node {node_id} endpoint {endpoint}: no counter change — no row written")
            return

        row = await self._build_row(entry, cumulative, deltas, counter_reset, is_baseline)

        try:
            await self.record_writer(row)
        except Exception as e:
            # Leave the saved counters untouched. The next observation of this
            # endpoint recomputes its delta from the last *successfully written*
            # totals, so a failed write self-heals instead of losing presses.
            logger.error(
                f"[Dock] Write failed for node {node_id} endpoint {endpoint}: {e}. "
                "Counter state not advanced — the delta will be included in the next row.",
                exc_info=True,
            )
            return

        # Only advance the saved totals once the row is durably accepted.
        node_state = self._counters.setdefault(node_id, {}).setdefault(endpoint, {})
        node_state.update({attr: cumulative[attr] for attr in COUNTER_FIELDS})
        self._save_state()

        self._rows_written += 1
        logger.info(
            f"[Dock] {row.get('dock_name') or 'node ' + str(node_id)} "
            f"endpoint {endpoint}: presses {row['press_total_count']} "
            f"(+{row['press_total_delta']}), success {row['press_success_count']} "
            f"(+{row['press_success_delta']}), encoder {row['encoder_total_count']} "
            f"(+{row['encoder_total_delta']}), encoder success {row['encoder_success_count']} "
            f"(+{row['encoder_success_delta']})"
            f"{' [COUNTER RESET]' if counter_reset else ''}"
            f"{' [baseline]' if is_baseline else ''}"
        )

    async def _build_row(
        self,
        entry: Dict[str, Any],
        cumulative: Dict[int, int],
        deltas: Dict[int, int],
        counter_reset: bool,
        is_baseline: bool,
    ) -> Dict[str, Any]:
        node_id = entry["node_id"]
        endpoint = entry["endpoint"]
        now = datetime.now(self.tz)

        row: Dict[str, Any] = {
            "hub_id": self.hub_id,
            "record_id": f"{node_id}-{endpoint}-{int(now.timestamp() * 1000)}",
            "timestamp": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "hour": now.hour,
            "day_of_week": now.strftime("%A"),
            "matter_node_id": str(node_id),
            "endpoint": endpoint,
            "product_name": entry.get("product_name") or "",
            "cluster_id": entry.get("cluster_id"),
            "counter_reset": counter_reset,
            "source": "baseline" if is_baseline else (entry.get("source") or "push"),
        }

        for attribute, (total_field, delta_field) in COUNTER_FIELDS.items():
            row[total_field] = cumulative.get(attribute, 0)
            row[delta_field] = deltas.get(attribute, 0)

        row.update(await self._resolve_identity(node_id, endpoint))
        return row

    async def _resolve_identity(self, node_id: int, endpoint: int) -> Dict[str, Any]:
        """Resolves dock/docklet/room names from the Custom Storage cache.

        Never raises and never blocks a row: telemetry counters are the valuable
        part, and a missing name is recoverable on the next observation once the
        Custom Storage poller catches up.
        """
        identity: Dict[str, Any] = {
            "dock_id": "",
            "dock_name": "",
            "docklet_id": "",
            "docklet_label": "",
            "room": "",
            "floor": "",
        }

        try:
            metadata = await self.metadata_provider()
        except Exception as e:
            logger.debug(f"[Dock] Custom Storage metadata unavailable: {e}")
            return identity

        docks = metadata.get("docks") or {}
        snaps = metadata.get("snaps") or {}
        rooms = metadata.get("rooms") or {}

        matched_id, matched = self._find_device(node_id, docks, snaps)

        if matched is None:
            self._warn_unmatched(node_id, docks, snaps)
            return identity

        identity["dock_id"] = _clean(matched.get("dock_id")) or str(matched_id or "")
        identity["dock_name"] = _first(matched, _LABEL_KEYS) or ""

        room_id = _first(matched, _ROOM_ID_KEYS)
        if room_id and room_id in rooms:
            room_info = rooms[room_id] or {}
            identity["room"] = _clean(room_info.get("name")) or ""
            identity["floor"] = _clean(room_info.get("floor_name")) or ""

        for docklet_key, docklet, implicit in _iter_docklets(matched):
            if _docklet_position(docklet_key, docklet, implicit) != endpoint:
                continue
            identity["docklet_id"] = _first(docklet, _DOCKLET_ID_KEYS) or str(docklet_key)
            # An unbound docklet reports "not_mapped", which _clean discards —
            # the label stays empty until a device is bound in the app rather
            # than inventing a name for it.
            identity["docklet_label"] = _first(docklet, _DOCKLET_LABEL_KEYS) or ""
            break
        else:
            if (node_id, endpoint) not in self._docklet_warned:
                self._docklet_warned.add((node_id, endpoint))
                shapes = [
                    {"key": k, "fields": sorted(d)} for k, d, _ in _iter_docklets(matched)
                ]
                logger.warning(
                    f"[Dock] Dock '{identity['dock_name'] or matched_id}' has no docklet at "
                    f"endpoint {endpoint} — docklet_id/docklet_label left empty. "
                    f"Docklet entries seen: {shapes or 'none'}"
                )

        return identity

    def _find_device(self, node_id: int, docks: Dict[str, Any],
                     snaps: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Finds the Custom Storage entry for a Matter node.

        Docks are searched before snaps: the Matter ProductName has already
        proven this node is a dock, so if the app filed it under snaps we still
        want its name rather than a blank row.
        """
        containers = (("docks", docks), ("snaps", snaps))

        # 1. The device states its own Matter node id.
        for container_name, container in containers:
            for device_id, device in container.items():
                if isinstance(device, dict) and _device_matches_node(device, node_id):
                    if container_name == "snaps":
                        self._warn_once(
                            f"snap-filed-{node_id}",
                            f"[Dock] Matter node {node_id} is a dock by ProductName but is "
                            f"stored under 'snaps' as '{device_id}'. Using it anyway.",
                        )
                    return device_id, device

        # 2. No usable node id — resolve through Home Assistant's device
        #    registry instead, using the docklet entities the app did record.
        #    This is what makes already-commissioned docks work without
        #    re-commissioning them when the app saved matter_node_id as null.
        if self.enricher is not None:
            for container_name, container in containers:
                for device_id, device in container.items():
                    if not isinstance(device, dict):
                        continue
                    if _entry_node_id(device) is not None:
                        continue  # it named a node, just not this one
                    if self._matches_via_registry(device, node_id):
                        self._warn_once(
                            f"registry-matched-{node_id}",
                            f"[Dock] Custom Storage entry '{device_id}' has no matter_node_id; "
                            f"matched it to Matter node {node_id} through Home Assistant's "
                            "device registry. Re-saving the dock in the app would make this direct.",
                        )
                        return device_id, device

        # 3. Last resort: exactly one dock in Custom Storage, exactly one dock
        #    node on the fabric, and no node id recorded — the mapping is
        #    unambiguous, so use it rather than emit nameless rows.
        if len(docks) == 1 and len(self._seen_nodes) <= 1:
            device_id, device = next(iter(docks.items()))
            if isinstance(device, dict) and _entry_node_id(device) is None:
                self._warn_once(
                    f"sole-dock-{node_id}",
                    f"[Dock] Custom Storage has exactly one dock ('{device_id}') with no "
                    f"matter_node_id, and node {node_id} is the only dock on the fabric — "
                    "pairing them. Fix matter_node_id in the app to make this explicit.",
                )
                return device_id, device

        return None, None

    def _matches_via_registry(self, device: Dict[str, Any], node_id: int) -> bool:
        """Resolves a device's own entities to a Matter node via HA's registry.

        Only the docklet's *own* entity id is used — never
        ``bound_device_entity_id``, which points at the controlled device on a
        completely different node.
        """
        candidates = []
        for key in ("entity_id", "entityId"):
            value = _clean(device.get(key))
            if value:
                candidates.append(value)
        for _key, docklet, _implicit in _iter_docklets(device):
            for key in ("entity_id", "entityId"):
                value = _clean(docklet.get(key))
                if value:
                    candidates.append(value)

        for entity_id in candidates:
            try:
                resolved = self.enricher.resolve_matter_node_id(entity_id=entity_id)
            except Exception:
                continue
            if resolved and match_node_id(node_id, resolved):
                return True
        return False

    def _warn_once(self, token: str, message: str):
        if token in self._warned_tokens:
            return
        self._warned_tokens.add(token)
        logger.warning(message)

    def _warn_unmatched(self, node_id: int, docks: Dict[str, Any], snaps: Dict[str, Any]):
        """Says exactly what Custom Storage holds, so the cause is obvious."""
        if node_id in self._unmatched_warned:
            return
        self._unmatched_warned.add(node_id)

        def summarize(container):
            return {
                device_id: {
                    "matter_node_id": _entry_node_id(device),
                    "name": _first(device, _LABEL_KEYS),
                    "entities": [
                        _clean(d.get("entity_id"))
                        for _k, d, _i in _iter_docklets(device)
                    ] or None,
                }
                for device_id, device in container.items()
                if isinstance(device, dict)
            }

        logger.warning(
            f"[Dock] Matter node {node_id} does not match any Custom Storage device — "
            "counters are recorded but dock_id/dock_name/docklet fields are empty. "
            f"Docks: {summarize(docks) or '{}'}. Snaps: {summarize(snaps) or '{}'}. "
            "Most likely the app saved matter_node_id as null and none of the docklet "
            "entities are in Home Assistant's device registry yet."
        )

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #

    def status(self) -> Dict[str, Any]:
        return {
            "rows_written": self._rows_written,
            "rows_skipped_unchanged": self._rows_skipped,
            "pending": len(self._pending),
            "tracked_nodes": sorted(self._counters),
        }
