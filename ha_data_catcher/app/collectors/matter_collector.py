"""Matter Server collector for Schnell dock hardware counters.

Connects directly to the Matter Server add-on's WebSocket (default
``ws://core-matter-server:5580/ws``) and watches the vendor-specific cluster
that Schnell dock firmware uses to expose its own press/encoder counters.

Why the Matter Server and not Home Assistant's entity layer: HA does not
surface manufacturer-specific clusters as entities, so the counters are only
reachable by talking to the Matter Server directly.

Two update paths run at the same time, deliberately:

* **push** — ``attribute_updated`` events, arriving the moment the firmware
  reports a counter change. Zero polling cost, but only fires for attributes
  the server actually holds a subscription on.
* **poll** — a periodic ``read_attribute`` *live device read* (not a cache
  read). This is the guaranteed path: it works even when the firmware does not
  report on the custom cluster, in which case push never fires at all.

Nothing here writes anywhere. Observed counter values are handed to a callback
as raw snapshots; :mod:`processors.dock_telemetry` owns all state and output.
"""

import asyncio
import json
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

import websockets

from logger import logger

# Basic Information cluster (0x0028) — every Matter node exposes this on
# endpoint 0. Attribute 3 is ProductName, which is how a dock identifies
# itself ("Dock_6D"); attribute 1 is VendorName ("Schnell Energy").
BASIC_INFO_CLUSTER = 40
ATTR_PRODUCT_NAME = 3
ATTR_VENDOR_NAME = 1

# The four dock counters we collect, on the vendor-specific cluster.
#   2 = total press count            3 = successful press count
#   4 = total encoder inc/dec count  5 = successful encoder inc/dec count
COUNTER_ATTRIBUTES = (2, 3, 4, 5)

# Matter manufacturer-extensible cluster IDs are (vendor_id << 16) | 0xFCxx,
# so any cluster whose low half is >= 0xFC00 is vendor-specific rather than
# standard. Used to auto-detect the dock cluster when the configured ID is
# absent — firmware moving from the test vendor ID to a real Schnell VID
# changes the cluster ID, and a hardcoded constant would silently read zeros
# forever.
MFG_CLUSTER_SUFFIX_MIN = 0xFC00

# Attribute keys from the Matter Server are flat "<endpoint>/<cluster>/<attribute>".
_ATTR_KEY_RE = re.compile(r"^(\d+)/(\d+)/(\d+)$")

_COMMAND_TIMEOUT = 30.0  # Thread round-trips through a live device read are slow
_RECONNECT_MIN = 5
_RECONNECT_MAX = 60


class UnsupportedMatterServer(Exception):
    """The Matter Server speaks a protocol this collector cannot drive."""


def parse_endpoint_range(spec: str) -> List[int]:
    """Parses an endpoint spec like ``"1-6"`` or ``"1,2,5"`` into a list."""
    endpoints: List[int] = []
    for chunk in str(spec or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            try:
                start, end = (int(p) for p in chunk.split("-", 1))
            except ValueError:
                logger.warning(f"[Matter] Ignoring malformed endpoint range '{chunk}'")
                continue
            endpoints.extend(range(min(start, end), max(start, end) + 1))
        else:
            try:
                endpoints.append(int(chunk))
            except ValueError:
                logger.warning(f"[Matter] Ignoring malformed endpoint '{chunk}'")
    if not endpoints:
        endpoints = list(range(1, 7))
        logger.warning(f"[Matter] Endpoint spec '{spec}' unusable — defaulting to 1-6")
    # Endpoint 0 is the root node; it never carries docklet counters.
    return sorted({ep for ep in endpoints if ep > 0})


class DockNode:
    """A Matter node classified as a Schnell dock."""

    def __init__(self, node_id: int, product_name: str, cluster_id: int,
                 endpoints: Sequence[int], vendor_name: str = "",
                 available: bool = True):
        self.node_id = node_id
        self.product_name = product_name
        self.vendor_name = vendor_name
        self.cluster_id = cluster_id
        self.endpoints = list(endpoints)
        self.available = available

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (f"DockNode(node_id={self.node_id}, product={self.product_name!r}, "
                f"cluster={self.cluster_id}, endpoints={self.endpoints})")


class MatterDockCollector:
    """Watches Schnell dock counters on the Matter Server WebSocket."""

    def __init__(
        self,
        ws_url: str,
        snapshot_callback: Callable[[Dict[str, Any]], None],
        product_name_prefixes: Sequence[str] = ("Dock_",),
        cluster_id: int = 0,
        endpoints: Optional[Sequence[int]] = None,
        poll_interval: int = 900,
    ):
        self.ws_url = ws_url
        self.snapshot_callback = snapshot_callback
        self.product_name_prefixes = [p.strip().lower() for p in product_name_prefixes if str(p).strip()]
        self.configured_cluster_id = int(cluster_id or 0)
        self.endpoints = list(endpoints) if endpoints else list(range(1, 7))
        self.poll_interval = max(60, int(poll_interval or 900))

        self._running = True
        self._ws: Optional[Any] = None
        self._msg_id = 0
        self._pending: Dict[str, asyncio.Future] = {}
        self._dock_nodes: Dict[int, DockNode] = {}

        # Tri-state: None = untested, True/False = wildcard reads supported or not.
        self._wildcard_reads: Optional[bool] = None

        # Suppresses repeat warnings when live reads keep coming back empty.
        self._poll_warned = False

        # Set once a protocol mismatch is confirmed, so we stop retrying a
        # server we cannot drive instead of reconnect-looping forever.
        self._unsupported = False

        self.is_connected = False

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    async def run(self):
        """Connection supervisor. Reconnects with backoff until stopped."""
        logger.info(f"[Matter] Dock telemetry collector starting — server: {self.ws_url}")
        backoff = _RECONNECT_MIN

        while self._running:
            try:
                await self._session()
                backoff = _RECONNECT_MIN
            except UnsupportedMatterServer as e:
                logger.error(
                    f"[Matter] Dock telemetry DISABLED — {e}. "
                    "Home Assistant event collection is unaffected and keeps running."
                )
                self._unsupported = True
                return
            except asyncio.CancelledError:
                raise
            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                logger.warning(f"[Matter] Connection lost/refused: {e}. Retrying in {backoff}s...")
            except Exception as e:
                logger.error(f"[Matter] Unexpected collector error: {e}", exc_info=True)
            finally:
                self.is_connected = False
                self._fail_pending("connection closed")

            if not self._running:
                break
            await asyncio.sleep(backoff)
            backoff = min(_RECONNECT_MAX, backoff * 2)

    async def _session(self):
        """One full connection: handshake, baseline, then listen + poll."""
        side_tasks: List[asyncio.Task] = []

        async with websockets.connect(self.ws_url, max_size=None) as ws:
            self._ws = ws
            self.is_connected = True

            # The Matter Server greets with an unsolicited server-info frame
            # before answering any command. Consume it before the reader task
            # starts so it cannot be mistaken for a command response.
            await self._consume_server_info(ws)

            reader_task = asyncio.create_task(self._reader_loop(ws))
            side_tasks.append(reader_task)

            nodes = await self._start_listening()
            self._rebuild_dock_map(nodes)

            # Baseline runs as a task, not inline: a slow or unresponsive dock
            # must not delay the reconciliation loop or the event stream.
            side_tasks.append(asyncio.create_task(self._baseline_reads()))
            side_tasks.append(asyncio.create_task(self._poll_loop()))

            try:
                await reader_task
            finally:
                for task in side_tasks:
                    if not task.done():
                        task.cancel()
                self._ws = None

    async def _consume_server_info(self, ws) -> Dict[str, Any]:
        """Reads and reports the server's greeting frame."""
        try:
            info = json.loads(await asyncio.wait_for(ws.recv(), timeout=_COMMAND_TIMEOUT))
        except asyncio.TimeoutError:
            raise UnsupportedMatterServer("no server-info frame within 30s of connecting")

        if not isinstance(info, dict):
            raise UnsupportedMatterServer(f"server-info frame was not an object: {type(info).__name__}")

        # Not fatal if these are missing — a compatible server with a different
        # greeting still gets a chance to answer start_listening. Only an
        # actually-rejected command disables the feature.
        known = {"fabric_id", "compressed_fabric_id", "schema_version", "sdk_version", "server_version"}
        if not known & set(info):
            logger.warning(
                "[Matter] Unrecognised server-info frame "
                f"(keys: {sorted(info)}). Attempting start_listening anyway."
            )
        else:
            logger.info(
                "[Matter] Connected to Matter Server — "
                f"schema_version={info.get('schema_version')} sdk_version={info.get('sdk_version')}"
            )
        return info

    async def _reader_loop(self, ws):
        """Dispatches every inbound frame to a pending command or an event."""
        while self._running:
            raw = await ws.recv()
            try:
                msg = json.loads(raw)
            except (TypeError, ValueError):
                logger.debug("[Matter] Skipping non-JSON frame")
                continue
            if not isinstance(msg, dict):
                continue

            if "event" in msg:
                self._handle_event(msg)
                continue

            msg_id = msg.get("message_id")
            if msg_id is None:
                continue
            future = self._pending.pop(str(msg_id), None)
            if future is None or future.done():
                continue
            if "error_code" in msg:
                future.set_exception(RuntimeError(
                    f"error_code={msg.get('error_code')} details={msg.get('details')}"
                ))
            else:
                future.set_result(msg.get("result"))

    async def _command(self, command: str, args: Optional[Dict[str, Any]] = None,
                       timeout: float = _COMMAND_TIMEOUT) -> Any:
        """Sends a command and awaits its response over the shared connection."""
        ws = self._ws
        if ws is None:
            raise ConnectionError("Matter Server connection is not open")

        self._msg_id += 1
        msg_id = str(self._msg_id)
        payload: Dict[str, Any] = {"message_id": msg_id, "command": command}
        if args:
            payload["args"] = args

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        try:
            await ws.send(json.dumps(payload))
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(msg_id, None)

    async def _start_listening(self) -> List[Dict[str, Any]]:
        """Subscribes to the event stream and returns the full node dump.

        ``start_listening`` does double duty in the Matter Server protocol: it
        returns every known node *and* opens the live event stream, so one call
        replaces a separate ``get_nodes``.
        """
        try:
            result = await self._command("start_listening")
        except RuntimeError as e:
            raise UnsupportedMatterServer(f"server rejected 'start_listening' ({e})")
        except asyncio.TimeoutError:
            raise UnsupportedMatterServer("server did not answer 'start_listening' within 30s")

        if not isinstance(result, list):
            raise UnsupportedMatterServer(
                f"'start_listening' returned {type(result).__name__}, expected a list of nodes"
            )
        logger.info(f"[Matter] Subscribed to event stream — {len(result)} node(s) reported")
        return result

    def _fail_pending(self, reason: str):
        for msg_id, future in list(self._pending.items()):
            if not future.done():
                future.set_exception(ConnectionError(reason))
            self._pending.pop(msg_id, None)

    def stop(self):
        """Signals the collector to stop reconnecting and exit."""
        self._running = False

    # ------------------------------------------------------------------ #
    # Dock classification
    # ------------------------------------------------------------------ #

    def _rebuild_dock_map(self, nodes: Sequence[Dict[str, Any]]):
        """Classifies every reported node, keeping only the docks."""
        docks: Dict[int, DockNode] = {}
        for node in nodes:
            dock = self._classify_node(node)
            if dock:
                docks[dock.node_id] = dock

        self._dock_nodes = docks
        if docks:
            for dock in docks.values():
                logger.info(
                    f"[Matter] Dock detected — node {dock.node_id} "
                    f"('{dock.product_name}') cluster {dock.cluster_id} "
                    f"(0x{dock.cluster_id:08X}) endpoints {dock.endpoints}"
                )
        else:
            logger.warning(
                "[Matter] No dock nodes found. Expected a node whose ProductName "
                f"starts with one of {self.product_name_prefixes} "
                "(Basic Information cluster 40, attribute 3)."
            )

    def _classify_node(self, node: Dict[str, Any]) -> Optional[DockNode]:
        """Returns a DockNode if this Matter node is a Schnell dock."""
        if not isinstance(node, dict):
            return None
        node_id = node.get("node_id")
        attributes = node.get("attributes")
        if node_id is None or not isinstance(attributes, dict):
            return None

        product_name = str(attributes.get(f"0/{BASIC_INFO_CLUSTER}/{ATTR_PRODUCT_NAME}") or "")
        vendor_name = str(attributes.get(f"0/{BASIC_INFO_CLUSTER}/{ATTR_VENDOR_NAME}") or "")

        name_match = any(product_name.lower().startswith(p) for p in self.product_name_prefixes)

        cluster_id = self._resolve_cluster_id(int(node_id), attributes, name_match)
        if cluster_id is None:
            if name_match:
                logger.warning(
                    f"[Matter] Node {node_id} ('{product_name}') matches a dock product name "
                    "but exposes no vendor counter cluster — skipping. "
                    f"Clusters seen: {sorted(self._clusters_present(attributes))}"
                )
            return None

        if not name_match:
            # Belt-and-braces: a dock whose ProductName has not been read yet
            # (node commissioned but not fully interviewed) still carries the
            # counter cluster. Collect it rather than lose the data.
            logger.warning(
                f"[Matter] Node {node_id} exposes dock counter cluster {cluster_id} "
                f"but ProductName is '{product_name or 'unknown'}' — collecting anyway."
            )

        endpoints = self._detect_endpoints(attributes, cluster_id)
        return DockNode(
            node_id=int(node_id),
            product_name=product_name,
            vendor_name=vendor_name,
            cluster_id=cluster_id,
            endpoints=endpoints,
            available=bool(node.get("available", True)),
        )

    def _resolve_cluster_id(self, node_id: int, attributes: Dict[str, Any],
                            name_match: bool) -> Optional[int]:
        """Config first, then auto-detect the vendor-specific counter cluster."""
        if self.configured_cluster_id:
            if self._cluster_present(attributes, self.configured_cluster_id):
                return self.configured_cluster_id
            if name_match:
                logger.warning(
                    f"[Matter] Node {node_id}: configured cluster "
                    f"{self.configured_cluster_id} (0x{self.configured_cluster_id:08X}) not present "
                    "— falling back to auto-detection."
                )

        # Score every vendor-specific cluster that carries counter attributes on
        # the endpoints we care about, and take the most widely present one.
        scores: Dict[int, int] = {}
        for key in attributes:
            parsed = _ATTR_KEY_RE.match(str(key))
            if not parsed:
                continue
            endpoint, cluster, attribute = (int(g) for g in parsed.groups())
            if endpoint not in self.endpoints:
                continue
            if attribute not in COUNTER_ATTRIBUTES:
                continue
            if (cluster & 0xFFFF) < MFG_CLUSTER_SUFFIX_MIN:
                continue
            scores[cluster] = scores.get(cluster, 0) + 1

        if not scores:
            return None

        best = max(scores.items(), key=lambda item: (item[1], -item[0]))[0]
        if best != self.configured_cluster_id:
            logger.info(
                f"[Matter] Node {node_id}: auto-detected dock counter cluster "
                f"{best} (0x{best:08X}) on {scores[best]} attribute path(s)."
            )
        return best

    def _cluster_present(self, attributes: Dict[str, Any], cluster_id: int) -> bool:
        return any(
            f"{ep}/{cluster_id}/{attr}" in attributes
            for ep in self.endpoints
            for attr in COUNTER_ATTRIBUTES
        )

    @staticmethod
    def _clusters_present(attributes: Dict[str, Any]) -> set:
        clusters = set()
        for key in attributes:
            parsed = _ATTR_KEY_RE.match(str(key))
            if parsed:
                clusters.add(int(parsed.group(2)))
        return clusters

    def _detect_endpoints(self, attributes: Dict[str, Any], cluster_id: int) -> List[int]:
        """Endpoints that actually expose the counter cluster."""
        found = [
            ep for ep in self.endpoints
            if any(f"{ep}/{cluster_id}/{attr}" in attributes for attr in COUNTER_ATTRIBUTES)
        ]
        if found:
            return found
        logger.warning(
            f"[Matter] Counter cluster {cluster_id} present but no endpoint in "
            f"{self.endpoints} exposes it in the server cache — will poll the full "
            "configured range instead."
        )
        return list(self.endpoints)

    # ------------------------------------------------------------------ #
    # Push path — attribute_updated events
    # ------------------------------------------------------------------ #

    def _handle_event(self, msg: Dict[str, Any]):
        event = msg.get("event")
        data = msg.get("data")

        if event == "attribute_updated":
            self._handle_attribute_updated(data)
        elif event in ("node_added", "node_updated"):
            self._handle_node_change(event, data)
        elif event == "node_removed":
            node_id = data if isinstance(data, int) else (data or {}).get("node_id")
            if node_id is not None and int(node_id) in self._dock_nodes:
                logger.info(f"[Matter] Dock node {node_id} removed from the fabric")
                self._dock_nodes.pop(int(node_id), None)

    def _handle_attribute_updated(self, data: Any):
        """``data`` is ``[node_id, "<ep>/<cluster>/<attr>", value]``."""
        if not isinstance(data, (list, tuple)) or len(data) < 3:
            return
        node_id, path, value = data[0], str(data[1]), data[2]

        dock = self._dock_nodes.get(int(node_id)) if node_id is not None else None
        if dock is None:
            return

        parsed = _ATTR_KEY_RE.match(path)
        if not parsed:
            return
        endpoint, cluster, attribute = (int(g) for g in parsed.groups())
        if cluster != dock.cluster_id or attribute not in COUNTER_ATTRIBUTES:
            return
        if endpoint not in dock.endpoints:
            # A previously-unseen endpoint started reporting — start tracking it.
            dock.endpoints.append(endpoint)
            dock.endpoints.sort()

        numeric = _as_int(value)
        if numeric is None:
            logger.debug(f"[Matter] Ignoring non-numeric counter at {path}: {value!r}")
            return

        logger.debug(f"[Matter] push node={node_id} {path} = {numeric}")
        self._emit(dock, endpoint, {attribute: numeric}, source="push")

    def _handle_node_change(self, event: str, data: Any):
        """Keeps the dock map current when nodes are added or re-interviewed."""
        if not isinstance(data, dict):
            return
        node_id = data.get("node_id")
        if node_id is None:
            return

        dock = self._classify_node(data)
        was_known = int(node_id) in self._dock_nodes

        if dock is None:
            if was_known:
                logger.info(f"[Matter] Node {node_id} no longer classifies as a dock")
                self._dock_nodes.pop(int(node_id), None)
            return

        self._dock_nodes[dock.node_id] = dock
        if not was_known:
            logger.info(
                f"[Matter] Dock discovered via {event} — node {dock.node_id} "
                f"('{dock.product_name}') cluster {dock.cluster_id} endpoints {dock.endpoints}"
            )
        # A re-interview refreshes cached counters; treat them as observations.
        self._emit_node_attributes(dock, data.get("attributes") or {}, source="poll")

    # ------------------------------------------------------------------ #
    # Poll path — guaranteed live device reads
    # ------------------------------------------------------------------ #

    async def _poll_loop(self):
        """Reconciliation reads, so counters land even if push never fires."""
        logger.info(
            f"[Matter] Reconciliation poll every {self.poll_interval}s "
            "(live device reads — independent of firmware attribute reporting)"
        )
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval)
                if not self._running or self._ws is None:
                    continue
                await self._poll_all_docks()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[Matter] Reconciliation poll failed: {e}")

    async def _poll_all_docks(self):
        for dock in list(self._dock_nodes.values()):
            if not dock.available:
                logger.debug(f"[Matter] Skipping poll of unavailable node {dock.node_id}")
                continue
            try:
                await self._poll_dock(dock)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[Matter] Poll of node {dock.node_id} failed: {e}")

    async def _poll_dock(self, dock: DockNode):
        """Reads all four counters on every endpoint of one dock."""
        readings = await self._read_dock_wildcard(dock)
        if readings is None:
            readings = await self._read_dock_discrete(dock)

        if not readings:
            # Worth a real warning once: if reads never succeed, the guaranteed
            # path is gone and telemetry depends entirely on the firmware
            # reporting changes by itself.
            if not self._poll_warned:
                self._poll_warned = True
                logger.warning(
                    f"[Matter] Live counter reads returned nothing for node {dock.node_id}. "
                    "Dock telemetry will rely on reported attribute updates only. "
                    "Enable the 'debug' option to see the individual read failures."
                )
            else:
                logger.debug(f"[Matter] Poll returned no counters for node {dock.node_id}")
            return

        self._poll_warned = False

        for endpoint, counters in readings.items():
            self._emit(dock, endpoint, counters, source="poll")

    async def _read_dock_wildcard(self, dock: DockNode) -> Optional[Dict[int, Dict[int, int]]]:
        """One wildcard read for the whole cluster, when the server supports it."""
        if self._wildcard_reads is False:
            return None

        path = f"*/{dock.cluster_id}/*"
        try:
            result = await self._command(
                "read_attribute",
                {"node_id": dock.node_id, "attribute_path": path},
            )
        except Exception as e:
            if self._wildcard_reads is None:
                logger.info(
                    f"[Matter] Wildcard reads unsupported ({e}) — "
                    "using discrete per-attribute reads from now on."
                )
                self._wildcard_reads = False
            return None

        readings = self._collect_paths(result if isinstance(result, dict) else {}, dock)
        if not readings:
            if self._wildcard_reads is None:
                logger.info(
                    "[Matter] Wildcard read returned nothing usable — "
                    "using discrete per-attribute reads from now on."
                )
                self._wildcard_reads = False
            return None

        if self._wildcard_reads is None:
            logger.info("[Matter] Wildcard cluster reads supported — 1 read per dock per poll.")
            self._wildcard_reads = True
        return readings

    async def _read_dock_discrete(self, dock: DockNode) -> Dict[int, Dict[int, int]]:
        """Fallback: one read per endpoint/attribute pair."""
        readings: Dict[int, Dict[int, int]] = {}
        for endpoint in dock.endpoints:
            for attribute in COUNTER_ATTRIBUTES:
                path = f"{endpoint}/{dock.cluster_id}/{attribute}"
                try:
                    result = await self._command(
                        "read_attribute",
                        {"node_id": dock.node_id, "attribute_path": path},
                    )
                except Exception as e:
                    logger.debug(f"[Matter] Read {path} on node {dock.node_id} failed: {e}")
                    continue

                # Concrete paths may still come back wrapped in a path->value dict.
                value = result.get(path, result) if isinstance(result, dict) else result
                numeric = _as_int(value)
                if numeric is not None:
                    readings.setdefault(endpoint, {})[attribute] = numeric
        return readings

    def _collect_paths(self, path_map: Dict[str, Any], dock: DockNode) -> Dict[int, Dict[int, int]]:
        """Filters a path->value map down to this dock's counter attributes."""
        readings: Dict[int, Dict[int, int]] = {}
        for key, value in path_map.items():
            parsed = _ATTR_KEY_RE.match(str(key))
            if not parsed:
                continue
            endpoint, cluster, attribute = (int(g) for g in parsed.groups())
            if cluster != dock.cluster_id or attribute not in COUNTER_ATTRIBUTES:
                continue
            if endpoint not in self.endpoints:
                continue
            numeric = _as_int(value)
            if numeric is not None:
                readings.setdefault(endpoint, {})[attribute] = numeric
        return readings

    # ------------------------------------------------------------------ #
    # Emitting snapshots
    # ------------------------------------------------------------------ #

    async def _baseline_reads(self):
        """Establishes a starting point for every dock right after connecting.

        Runs immediately rather than waiting a full poll interval, so a restart
        captures the current absolute counters straight away.
        """
        if not self._dock_nodes:
            return
        logger.info(f"[Matter] Reading baseline counters for {len(self._dock_nodes)} dock(s)...")
        try:
            await self._poll_all_docks()
            logger.info("[Matter] Baseline counter read complete")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[Matter] Baseline read failed: {e}")

    def _emit_node_attributes(self, dock: DockNode, attributes: Dict[str, Any], source: str):
        readings = self._collect_paths(
            {k: v for k, v in attributes.items() if isinstance(k, str)}, dock
        )
        for endpoint, counters in readings.items():
            self._emit(dock, endpoint, counters, source=source)

    def _emit(self, dock: DockNode, endpoint: int, counters: Dict[int, int], source: str):
        """Hands one raw counter snapshot to the telemetry processor."""
        if not counters:
            return
        snapshot = {
            "node_id": dock.node_id,
            "product_name": dock.product_name,
            "vendor_name": dock.vendor_name,
            "cluster_id": dock.cluster_id,
            "endpoint": endpoint,
            "counters": dict(counters),
            "source": source,
        }
        try:
            self.snapshot_callback(snapshot)
        except Exception as e:
            logger.error(f"[Matter] Snapshot callback failed: {e}", exc_info=True)

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #

    def status(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected,
            "unsupported": self._unsupported,
            "dock_nodes": {d.node_id: d.product_name for d in self._dock_nodes.values()},
            "wildcard_reads": self._wildcard_reads,
        }


def _as_int(value: Any) -> Optional[int]:
    """Coerces a Matter attribute value to int, or None if it is not a count."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None
