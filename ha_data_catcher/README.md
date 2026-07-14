# HA Data Catcher

![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-03A9F4?style=flat-square&logo=home-assistant)
![Platform](https://img.shields.io/badge/Platform-Multi--Arch-E91E63?style=flat-square)
![Version](https://img.shields.io/badge/Version-1.0.0-4CAF50?style=flat-square)

Real-time telemetry pipeline for SMASH. Captures Home Assistant device events as they happen, enriches them with room, floor, and hardware context, and streams them to Firestore — where the Stream-to-BigQuery extension makes them queryable alongside app-side analytics.

---

## Overview

HA Data Catcher runs as a native Home Assistant OS add-on. On startup it:

1. Auto-discovers the Home Assistant connection details, hub ID, and timezone via the Supervisor API.
2. Opens a persistent WebSocket subscription to all Home Assistant events (`state_changed`, `call_service`, `automation_triggered`, and more).
3. Enriches each event with room, floor, and device-type metadata from the Custom Data Storage add-on and Home Assistant's own registries.
4. Writes each enriched event as a Firestore document under:

```
smash_db/<hub_mac>/ha_events/<event_id>
```

From there, the **Stream Firestore to BigQuery** extension syncs every document into the `schnell_analytics.ha_logs_raw_changelog` table, making hub-side telemetry queryable alongside the app-side `app_logs` table via the shared `trigger_id` key.

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

---

## Key Capabilities

- **Complete event capture** — subscribes to the full Home Assistant event bus, not a fixed entity list. New devices are covered automatically.
- **Origin classification** — every action is attributed to its true source (mobile app, HA UI, automation, scene, or physical device) using Home Assistant context tracking.
- **Trigger correlation** — a single user action that fans out to multiple entities shares one `trigger_id`; the initiating row is flagged `is_trigger` so analytics can count actions, not rows.
- **Metadata enrichment** — room, floor, and device type are resolved live from Custom Data Storage and refreshed every 30 seconds.
- **Noise filtering** — diagnostic chatter (sun, weather, network sensors, recorder statistics) is dropped at the source; duplicate states within 500 ms are deduplicated.
- **Self-healing** — the WebSocket reconnects automatically, registries refresh on change, and metadata polling recovers from transient failures without restart.

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

The mobile app's Home Assistant account is identified automatically — the app registers its own user ID in Custom Data Storage, and this add-on picks it up on its regular polling cycle. No configuration is required.

### Verify startup

Open the add-on's **Log** tab. A healthy start looks like:

```
[Firestore] Initialized. Hub path: smash_db/AA:BB:CC:DD:EE:FF/ha_events
[Startup] Discovery sequence complete.
Successfully authenticated with Home Assistant WebSocket
```

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
│   │   └── custom_storage_collector.py # Polls Custom Data Storage every 30 s
│   ├── processors/
│   │   ├── event_parser.py             # Raw HA event → structured record + event_id
│   │   ├── event_enricher.py           # Room/floor/device-type resolution + origin classification
│   │   ├── metrics_fields.py           # Latency and Matter/Thread timing metrics
│   │   └── filters.py                  # Noise filtering
│   └── firebase/
│       └── firestore_writer.py         # Firestore batch writer
├── Dockerfile
├── build.yaml
├── config.json
├── requirements.txt
└── run.sh
```

---

## Troubleshooting

**WebSocket keeps reconnecting** — check that Home Assistant Core is running and healthy; the add-on retries every 5 seconds and recovers automatically once Core responds.

**Events missing room/floor** — verify the Custom Data Storage add-on is running and reachable at the configured `custom_storage_url`, and that home setup data has been synced from the mobile app.

**`app:` vs `ha_ui:` classification inactive** — classification activates automatically once the mobile app has registered its identity in Custom Data Storage. Until then, app-originated events are attributed by hardware source only.

**No documents in Firestore** — check the add-on log for Firestore initialization errors, and confirm the hub has outbound internet access.

Enable the `debug` option for verbose per-event logging.
