# HA Data Catcher

![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-03A9F4?style=flat-square&logo=home-assistant)
![Platform](https://img.shields.io/badge/Platform-Multi--Arch-E91E63?style=flat-square)
![Version](https://img.shields.io/badge/Version-1.1.1-4CAF50?style=flat-square)

Real-time telemetry pipeline for SMASH. Captures Home Assistant device events as they happen and reads dock hardware counters straight off the Matter Server, enriches both with room, floor, and hardware context, and streams them to Firestore — where the Stream-to-BigQuery extension makes them queryable alongside app-side analytics.

---

## Overview

HA Data Catcher runs as a native Home Assistant OS add-on and collects two independent streams.

**Home Assistant events.** On startup it:

1. Auto-discovers the Home Assistant connection details, hub ID, and timezone via the Supervisor API.
2. Opens a persistent WebSocket subscription to all Home Assistant events (`state_changed`, `call_service`, `automation_triggered`, and more).
3. Enriches each event with room, floor, and device-type metadata from the Custom Data Storage add-on and Home Assistant's own registries.
4. Writes each enriched event as a Firestore document under:

```
smash_db/<hub_mac>/ha_events/<event_id>
```

**Dock hardware counters.** In parallel it connects to the Matter Server add-on, identifies every commissioned dock, and watches the vendor-specific cluster where the firmware keeps its own press and encoder counters — data Home Assistant does not expose as entities. Each change is written under:

```
smash_db/<hub_mac>/dock_events/<record_id>
```

From there, the **Stream Firestore to BigQuery** extension syncs both collections into `schnell_analytics.ha_logs_raw_changelog` and `schnell_analytics.dock_logs_raw_changelog`, making hub-side telemetry queryable alongside the app-side `app_logs` table via the shared `trigger_id` key.

Dock telemetry is entirely optional and isolated: if the Matter Server is unavailable or no dock is commissioned, Home Assistant event collection continues untouched. Full detail in **[`DOCK_TELEMETRY.md`](DOCK_TELEMETRY.md)**.

---

## Data Flow

```
HA WebSocket
    │  state_changed / call_service / automation_triggered
    ▼
EventParser        generates event_id (UUID), timestamps, context fields
    ▼
EventEnricher      resolves room, floor, device_type from Custom Storage + HA registries
                   computes ha_processing_latency_ms
                   classifies true origin: log_source, trigger_id, is_trigger, actuation_source
    ▼
FirestoreWriter
    ▼
Firestore          smash_db/<hub_mac>/ha_events/<event_id>
    │  Stream Firestore to BigQuery extension
    ▼
BigQuery           schnell_analytics.ha_logs_raw_changelog
                   schnell_analytics.ha_logs_raw_latest   (view)
                   schnell_analytics.ha_logs              (flattened view — see BigQuery Setup)
```

```
Matter Server WebSocket
    │  attribute_updated events (push) + periodic live device reads (poll)
    ▼
MatterDockCollector       identifies docks by ProductName, resolves the vendor counter cluster
    ▼
DockTelemetryProcessor    cumulative → delta, reset detection, debounce
                          resolves dock_id / dock_name / docklet from Custom Storage
    ▼
FirestoreWriter
    ▼
Firestore          smash_db/<hub_mac>/dock_events/<record_id>
    │  Stream Firestore to BigQuery extension
    ▼
BigQuery           schnell_analytics.dock_logs_raw_changelog
                   schnell_analytics.dock_logs              (flattened view)
                   schnell_analytics.dock_logs_action_daily (compatibility view)
```

---

## Key Capabilities

- **Complete event capture** — subscribes to the full Home Assistant event bus, not a fixed entity list. New devices are covered automatically.
- **Origin classification** — every action is attributed to its true source (mobile app, HA UI, automation, scene, or physical device) using Home Assistant context tracking.
- **Trigger correlation** — a single user action that fans out to multiple entities shares one `trigger_id`; the initiating row is flagged `is_trigger` so analytics can count actions, not rows.
- **Metadata enrichment** — room, floor, and device type are resolved live from Custom Data Storage and refreshed every 30 seconds.
- **Noise filtering** — diagnostic chatter (sun, weather, network sensors, recorder statistics) is dropped at the source; duplicate states within 500 ms are deduplicated.
- **Dock hardware counters** — reads press and encoder counters directly from dock firmware over the Matter Server, including presses that never reached Home Assistant. Cumulative counters are converted to aggregatable deltas, dock reboots are detected rather than mis-counted, and the counter state survives add-on restarts.
- **Firmware-change resilient** — the dock's vendor-specific Matter cluster is auto-detected if the configured ID is absent, so a firmware vendor-ID change cannot silently reduce telemetry to zeros.
- **Self-healing** — both WebSockets reconnect automatically, registries refresh on change, and metadata polling recovers from transient failures without restart. A failed dock write is retried into the next row's delta rather than lost.

---

## Installation

1. Copy this folder into your Home Assistant `/addons/local/` directory (e.g. via the Samba share add-on).
2. In Home Assistant, go to **Settings → Add-ons → Add-on Store → ⋮ → Check for updates**.
3. Find **HA Data Catcher** under *Local add-ons* and click **Install**.
4. Configure the options below, then click **Start**.

### Configuration

| Option | Default | Description |
|---|---|---|
| `hub_id` | *(auto-discovered)* | The hub's MAC address (e.g. `AA:BB:CC:DD:EE:FF`). Must match the identifier used by the mobile app. Leave empty to auto-discover. |
| `custom_storage_url` | `http://homeassistant:8100` | Base URL of the Custom Data Storage add-on. |
| `ha_token` | *(empty)* | Long-lived Home Assistant access token. Only required when running outside the Supervisor (standalone/development); inside Home Assistant OS the add-on authenticates automatically. |
| `debug` | `false` | Enable verbose logging for troubleshooting. |
| `enable_dock_telemetry` | `true` | Collect dock hardware counters from the Matter Server. Set `false` to run Home Assistant event collection only. |
| `matter_server_url` | `ws://core-matter-server:5580/ws` | WebSocket URL of the Matter Server add-on. |
| `dock_product_names` | `Dock_` | Comma-separated Matter ProductName prefixes that identify a dock. |
| `dock_cluster_id` | `4294048801` | Vendor-specific Matter cluster holding the counters (`0xFFF1FC21`). Set `0` to rely on auto-detection only. |
| `dock_endpoints` | `1-6` | Endpoint range to scan for docklet counters. Accepts `1-6` or `1,2,5`. |
| `dock_poll_interval` | `900` | Seconds between reconciliation live device reads (60–86400). |
| `dock_min_write_interval` | `2` | Debounce window in seconds — coalesces the counters a single press bumps into one row (0–60). |

Dock options are ignored entirely when `enable_dock_telemetry` is `false`. See **[`DOCK_TELEMETRY.md`](DOCK_TELEMETRY.md)** for how each one behaves.

The mobile app's Home Assistant account is identified automatically — the app registers its own user ID in Custom Data Storage, and this add-on picks it up on its regular polling cycle. No configuration is required.

### Verify startup

Open the add-on's **Log** tab. A healthy start looks like:

```
[Firestore] Initialized. Hub path: smash_db/AA:BB:CC:DD:EE:FF/ha_events
[Startup] Discovery sequence complete.
Successfully authenticated with Home Assistant WebSocket
[App] Dock telemetry enabled — products ['Dock_'], cluster 4294048801, endpoints 1-6
[Matter] Dock detected — node 20 ('Dock_6D') cluster 4294048801 (0xFFF1FC21) endpoints [1, 2, 3, 4, 5, 6]
[Dock] Living Room Dock endpoint 1: presses 102 (+0), success 69 (+0), encoder 21 (+0), encoder success 21 (+0) [baseline]
```

The `[Matter]` and `[Dock]` lines appear only when dock telemetry is enabled and a dock is commissioned.

---

## Event Schema

Every document written to `ha_events` contains the following fields:

| Field | Description |
|---|---|
| `hub_id` | Hub MAC address (matches the `hub_id` configuration value) |
| `event_id` | UUID — Firestore document ID and join key to app-side events |
| `timestamp` | ISO-8601 event timestamp (hub-local timezone) |
| `date`, `time`, `hour`, `day_of_week` | Analytics-friendly time splits |
| `log_source` | True origin — `app:command`, `ha_ui:command`, `automation:<id>`, `scene:<id>`, or the hardware fallback `snap:<id>` / `dock:<id>` / `ha:<domain>` |
| `actuation_source` | Which hardware physically carried out the action — `snap:<id>` / `dock:<id>` / `ha:<domain>`. Always populated; `log_source` falls back to this when the true origin is unknown |
| `trigger_id` | Home Assistant context ID, shared by every row a single action produces — join key to `app_logs.trigger_id` |
| `is_trigger` | `true` on the one initiating row per action, `false` on fan-out rows. Count `WHERE is_trigger` to count actions |
| `use_case` | Always `Hub Observed` for hub-side events |
| `ha_event_type` | Home Assistant event type (`state_changed`, `call_service`, …) |
| `entity_id` | Entity that changed |
| `action` | `turn_on`, `turn_off`, `state_transition`, `trigger`, etc. |
| `old_state`, `new_state` | State before and after the change |
| `room`, `floor` | Resolved from Custom Data Storage metadata |
| `device_type` | Resolved load type (`Light`, `Fan`, `docklet`, …) |
| `origin` | `LOCAL` or `REMOTE` |
| `context_id` | Home Assistant internal transaction token |
| `context_user_id` | Home Assistant user that authenticated the change, if any |
| `docklet_id` | Docklet entity ID (dock events only) |
| `dock_id` | Dock hardware this entity is mapped to. An entity-to-hardware mapping, **not** an origin signal — any command on a dock-bound device carries it |
| `docklet_state_change_ts` | Timestamp of the docklet state change |
| `matter_command_ts` | Timestamp of the Matter-level command |
| `snap_state_change_ts` | Timestamp of the Snap device acknowledgement |
| `ha_processing_latency_ms` | `snap_state_change_ts − event_timestamp`, in milliseconds |
| `thread_node_id` | Matter/Thread node ID |

Fields with no value for a given event are omitted from the document.

---

## Noise Filtering

The following are dropped at the source and never written to Firestore:

- **Event types:** `time_changed`, `themes_updated`, `component_loaded`, `core_config_updated`, recorder statistics events
- **Domains:** `device_tracker`, `upnp`, `sun`, `zone`, `weather`
- **Entity prefixes:** router, network, Wi-Fi, ping, bandwidth, and uptime sensors
- **Rapid duplicates:** identical state changes on the same entity within 500 ms

Entities whose IDs contain `dock` or `snap` are always retained regardless of domain.

Noise filtering applies to the Home Assistant event stream only. Dock counters are read directly from hardware and are never filtered.

---

## Dock Counter Schema

Every document written to `dock_events` represents **one dock × one docklet endpoint × one observed change**. An idle dock writes nothing.

| Field | Description |
|---|---|
| `hub_id` | Hub MAC address |
| `record_id` | `<node_id>-<endpoint>-<unix_ms>` — Firestore document ID |
| `timestamp` | ISO-8601 observation timestamp (hub-local timezone) |
| `date`, `time`, `hour`, `day_of_week` | Analytics-friendly time splits |
| `matter_node_id` | Matter node ID of the dock |
| `dock_id`, `dock_name` | Resolved from Custom Data Storage — by the stored Matter node ID, else via Home Assistant's device registry, else by sole-dock pairing (see [`DOCK_TELEMETRY.md` §3](DOCK_TELEMETRY.md#3-how-a-dock-is-identified)) |
| `room`, `floor` | Resolved location of the dock |
| `endpoint` | Docklet position on the dock, 1–6 |
| `docklet_id`, `docklet_label` | Docklet entity ID and bound device label for that position |
| `press_total_count` | Cumulative total presses (Matter attribute 2) |
| `press_success_count` | Cumulative successful presses (attribute 3) |
| `encoder_total_count` | Cumulative encoder increment/decrement actions (attribute 4) |
| `encoder_success_count` | Cumulative successful encoder actions (attribute 5) |
| `press_total_delta`, `press_success_delta` | Change since the previous row — **use these to aggregate** |
| `encoder_total_delta`, `encoder_success_delta` | Change since the previous row |
| `counter_reset` | `true` when the dock rebooted and restarted its counters |
| `source` | `push` (firmware reported), `poll` (live device read), `baseline` (first sighting) |
| `product_name`, `cluster_id` | Matter ProductName and the vendor cluster actually read |

The firmware counters are cumulative, so `SUM()` the `*_delta` columns for "presses today" and read the `*_count` columns for lifetime totals. Failure counts are derived in the BigQuery view as `total_delta − success_delta`.

**Full pipeline documentation, BigQuery migration steps, view SQL, and analytics queries: [`DOCK_TELEMETRY.md`](DOCK_TELEMETRY.md).**

---

## BigQuery Setup (one-time)

### 1. Configure the Stream Firestore to BigQuery extension

In the Firebase Console, open **Extensions → Stream Firestore to BigQuery** and configure an instance with the collection group set to `ha_events` and the BigQuery table ID set to `ha_logs`. This produces the `ha_logs_raw_changelog` table and `ha_logs_raw_latest` view.

### 2. Create the flattened view

Run once in BigQuery:

```sql
CREATE OR REPLACE VIEW `schnell-home-automation.schnell_analytics.ha_logs` AS
SELECT
  JSON_VALUE(data, '$.hub_id')                                        AS hub_id,
  JSON_VALUE(data, '$.event_id')                                      AS event_id,
  JSON_VALUE(data, '$.timestamp')                                     AS event_timestamp,
  JSON_VALUE(data, '$.date')                                          AS date,
  JSON_VALUE(data, '$.time')                                          AS time,
  SAFE_CAST(JSON_VALUE(data, '$.hour') AS INT64)                      AS hour,
  JSON_VALUE(data, '$.day_of_week')                                   AS day_of_week,
  JSON_VALUE(data, '$.log_source')                                    AS log_source,
  JSON_VALUE(data, '$.use_case')                                      AS use_case,
  JSON_VALUE(data, '$.ha_event_type')                                 AS ha_event_type,
  JSON_VALUE(data, '$.entity_id')                                     AS entity_id,
  JSON_VALUE(data, '$.action')                                        AS action,
  JSON_VALUE(data, '$.old_state')                                     AS old_state,
  JSON_VALUE(data, '$.new_state')                                     AS new_state,
  JSON_VALUE(data, '$.room')                                          AS room,
  JSON_VALUE(data, '$.floor')                                         AS floor,
  JSON_VALUE(data, '$.device_type')                                   AS device_type,
  JSON_VALUE(data, '$.origin')                                        AS origin,
  JSON_VALUE(data, '$.context_id')                                    AS context_id,
  JSON_VALUE(data, '$.context_user_id')                               AS context_user_id,
  JSON_VALUE(data, '$.docklet_id')                                    AS docklet_id,
  JSON_VALUE(data, '$.dock_id')                                       AS dock_id,
  JSON_VALUE(data, '$.docklet_state_change_ts')                       AS docklet_state_change_ts,
  JSON_VALUE(data, '$.matter_command_ts')                             AS matter_command_ts,
  JSON_VALUE(data, '$.snap_state_change_ts')                          AS snap_state_change_ts,
  SAFE_CAST(JSON_VALUE(data, '$.ha_processing_latency_ms') AS INT64)  AS ha_processing_latency_ms,
  JSON_VALUE(data, '$.thread_node_id')                                AS thread_node_id,
  JSON_VALUE(data, '$.actuation_source')                              AS actuation_source,
  JSON_VALUE(data, '$.trigger_id')                                    AS trigger_id,
  SAFE_CAST(JSON_VALUE(data, '$.is_trigger') AS BOOL)                 AS is_trigger
FROM `schnell-home-automation.schnell_analytics.ha_logs_raw_latest`
WHERE data IS NOT NULL;
```

Query it:

```sql
SELECT *
FROM `schnell-home-automation.schnell_analytics.ha_logs`
ORDER BY event_timestamp DESC
LIMIT 200;
```

### 3. Configure the dock counter pipeline

Dock counters need a **second** extension instance (collection path `smash_db/{hubId}/dock_events`, table ID `dock_logs`) plus two views. Because this replaces the previous Google Sheet → BigQuery sync, the steps must be run in a specific order — see [`DOCK_TELEMETRY.md` §8](DOCK_TELEMETRY.md#8-migration-from-the-google-sheet-pipeline).

---

## Architecture

```
ha_data_catcher/
├── app/
│   ├── main.py                         # Orchestrator — wires all components
│   ├── startup.py                      # Discovery: HA connection details, timezone, hub_id
│   ├── supervisor.py                   # HA Supervisor API client
│   ├── config_manager.py               # Loads options.json / environment variables
│   ├── logger.py                       # Shared logger
│   ├── collectors/
│   │   ├── websocket_collector.py      # Persistent WebSocket connection + HA registry fetch
│   │   ├── custom_storage_collector.py # Polls Custom Data Storage every 30 s
│   │   └── matter_collector.py         # Matter Server WebSocket — dock discovery + counter reads
│   ├── processors/
│   │   ├── event_parser.py             # Raw HA event → structured record + event_id
│   │   ├── event_enricher.py           # Room/floor/device-type resolution + origin classification
│   │   ├── metrics_fields.py           # Latency and Matter/Thread timing metrics
│   │   ├── dock_telemetry.py           # Counter deltas, reset detection, dock identity resolution
│   │   └── filters.py                  # Noise filtering
│   └── firebase/
│       └── firestore_writer.py         # Firestore batch writer (ha_events + dock_events)
├── DOCK_TELEMETRY.md                   # Dock counter pipeline + BigQuery migration
├── Dockerfile
├── build.yaml
├── config.json
├── requirements.txt
└── run.sh
```

Runtime state kept on the hub:

| Path | Purpose |
|---|---|
| `/data/options.json` | Add-on configuration, written by the Supervisor |
| `/data/dock_counters.json` | Last-seen dock counters, so deltas survive restarts |

---

## Troubleshooting

**WebSocket keeps reconnecting** — check that Home Assistant Core is running and healthy; the add-on retries every 5 seconds and recovers automatically once Core responds.

**Events missing room/floor** — verify the Custom Data Storage add-on is running and reachable at the configured `custom_storage_url`, and that home setup data has been synced from the mobile app.

**`app:` vs `ha_ui:` classification inactive** — classification activates automatically once the mobile app has registered its identity in Custom Data Storage. Until then, app-originated events are attributed by hardware source only.

**No documents in Firestore** — check the add-on log for Firestore initialization errors, and confirm the hub has outbound internet access.

**No dock counters collected** — check the log for `[Matter]` lines. `No dock nodes found` means no commissioned node has a matching ProductName; verify it in the Matter Server dashboard and adjust `dock_product_names`. Connection errors mean the Matter Server add-on is not running or `matter_server_url` is wrong. Home Assistant event collection is unaffected either way.

**Dock counters arrive only every 15 minutes** — the firmware is not reporting attribute changes, so only the reconciliation poll sees them. This is accurate, just coarser; lower `dock_poll_interval` for finer granularity. The `source` column shows which path produced each row.

See [`DOCK_TELEMETRY.md` §10](DOCK_TELEMETRY.md#10-troubleshooting) for the full dock troubleshooting table.

Enable the `debug` option for verbose per-event logging.
