# HA Data Catcher

![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-03A9F4?style=flat-square&logo=home-assistant)
![Platform](https://img.shields.io/badge/Platform-Multi--Arch-E91E63?style=flat-square)
![Version](https://img.shields.io/badge/Version-2.0.0-4CAF50?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-FFC107?style=flat-square)

Streams Home Assistant device events to **Firestore** in real-time, enriched with room, floor, and hardware context from Custom Storage. The Firebase BigQuery extension then automatically syncs those events to BigQuery for fleet analytics — mirroring the same pipeline used by the Schnell mobile app.

---

## Overview

The **HA Data Catcher** runs directly on Home Assistant OS as an add-on. On startup it connects to the HA WebSocket to capture every device state change (`state_changed`, `call_service`, `automation_triggered`, etc.), enriches each event with room/floor/device-type metadata from the Custom Storage add-on (port 8100), and writes it to Firestore under:

```
smash_db/<hub_mac>/ha_events/<event_id>
```

From there the existing **Firebase → BigQuery** extension picks up every document and streams it into the `schnell_analytics.ha_logs_raw_changelog` table, making hub-side telemetry queryable alongside the app-side `app_logs` table.

---

## Data Flow

```
HA WebSocket
    ↓  state_changed / call_service / automation_triggered
EventParser      → generates event_id (UUID), timestamps, context fields
EventEnricher    → resolves room, floor, device_type from Custom Storage + HA registries
                 → computes ha_processing_latency_ms
                 → classifies true origin: log_source, trigger_id, is_trigger,
                   actuation_source (see the Event Schema section below)
FirestoreWriter
    ↓
Firestore:  smash_db/<hub_mac>/ha_events/<event_id>
    ↓  Firebase "Stream Firestore to BigQuery" extension
BigQuery:   schnell_analytics.ha_logs_raw_changelog
            schnell_analytics.ha_logs_raw_latest    (view)
            schnell_analytics.ha_logs               (flattened view — create manually, see below)
```

---

## Architecture

```
ha_data_catcher/                 (folder name changed a few times during dev —
├── app/                          always check the repo root for the current one)
│   ├── main.py                        # Orchestrator — wires all components
│   ├── startup.py                     # Discovery: HA connection details, timezone, hub_id
│   ├── supervisor.py                  # HA Supervisor API client
│   ├── config_manager.py              # Loads options.json / env vars
│   ├── logger.py                      # Shared logger
│   ├── collectors/
│   │   ├── websocket_collector.py     # Persistent WS connection + HA registry fetch
│   │   └── custom_storage_collector.py# Polls Custom Storage API every 30s (also
│   │                                  # picks up the app's self-reported HA account id)
│   ├── processors/
│   │   ├── event_parser.py            # Raw HA event → structured dict + event_id
│   │   ├── event_enricher.py          # Adds room/floor/device_type/latency fields +
│   │   │                              # true-origin classification (_classify_trigger)
│   │   ├── metrics_fields.py          # Computes ha_processing_latency_ms
│   │   └── filters.py                 # Drops noisy domains (sun, weather, etc.)
│   └── firebase/
│       └── firestore_writer.py        # Firebase Admin SDK batch writer
├── firebase-service-account.json      # ← Replace with your real service account key
├── Dockerfile
├── build.yaml
├── config.json
├── requirements.txt
└── run.sh
```

---

## Event Schema (`ha_events` document fields)

Every Firestore document written under `ha_events` contains these fields:

| Field | Description |
|---|---|
| `hub_id` | Hub MAC address (matches the `hub_id` config value) |
| `event_id` | UUID — Firestore doc id and future join key to `app_events` |
| `timestamp` | ISO-8601 event timestamp (local timezone) |
| `date`, `time`, `hour`, `day_of_week` | Analytics-friendly time splits |
| `log_source` | True origin — `app:command` / `ha_ui:command` / `automation:<id>` / `scene:<id>`, or the hardware fallback `snap:<id>` / `dock:<id>` / `ha:<domain>` |
| `actuation_source` | Which hardware physically carried it out — `snap:<id>` / `dock:<id>` / `ha:<domain>` (always populated; `log_source` falls back to this when true origin is unknown) |
| `trigger_id` | HA's own context id, shared by every row one action produces — join key to `app_logs.trigger_id` |
| `is_trigger` | `true` on the one initiating row per action; `false` on fan-out. **Count `WHERE is_trigger`**, not every row |
| `use_case` | Always `Hub Observed` for hub-side events |
| `ha_event_type` | HA internal type (`state_changed`, `call_service`, …) |
| `entity_id` | HA entity that changed |
| `action` | `turn_on` / `turn_off` / `state_transition` / `trigger` / etc. |
| `old_state`, `new_state` | State before and after the change |
| `room`, `floor` | Resolved from Custom Storage metadata |
| `device_type` | Resolved load type (`Light`, `Fan`, `docklet`, …) |
| `origin` | `LOCAL` or `REMOTE` |
| `context_id` | HA internal transaction token |
| `context_user_id` | HA user who authenticated the change, if any (compared against the app's self-reported id to help classify `log_source`) |
| `docklet_id` | Docklet entity ID (dock events only) |
| `dock_id` | Which dock's hardware this entity is mapped to — an entity-hardware mapping, **not** an origin signal; any command on a dock-bound device carries this, including app commands |
| `docklet_state_change_ts` | Timestamp of docklet state change |
| `matter_command_ts` | Timestamp of Matter-level command |
| `snap_state_change_ts` | Timestamp of Snap device acknowledgement |
| `ha_processing_latency_ms` | `snap_state_change_ts − event_timestamp` in ms |
| `thread_node_id` | Matter/Thread node ID |
| `network_type` | Always `local` |

**How the app's own account id is learned (added 2026-07-09, no config
anywhere):** the app captures its own `context.user_id` off a command
response and writes it once into Custom Storage. This add-on's existing
30-second Custom Storage poll picks it up automatically and feeds it to the
enricher, so `app:` vs `ha_ui:` classification activates on its own —
see `event_enricher.py` (`_classify_trigger`) and
`custom_storage_collector.py` (`_parse_app_identity`).

---

## Installation

### Before installing — add your Firebase credentials

Replace the placeholder `firebase-service-account.json` in this folder with your real Firebase service account key:

1. Firebase Console → Project Settings → Service accounts → **Generate new private key**
2. Rename the downloaded file to `firebase-service-account.json`
3. Replace the file in this folder with it

The Dockerfile bakes this file into the container at build time — no file editor or SSH needed after that.

### Install the add-on

1. Copy this folder into your HA's `/addons/local/` directory via Samba share
2. HA → Settings → Add-ons → Add-on Store → ⋮ → **Check for updates**
3. Find **HA Data Catcher** under Local add-ons → **Install**

### Configure

In the add-on's **Configuration** tab:

| Option | Description |
|---|---|
| `hub_id` | Your hub's raw MAC address (e.g. `AA:BB:CC:DD:EE:FF`) — must match what the mobile app stores |
| `custom_storage_url` | URL of the Custom Storage add-on (default: `http://homeassistant:8100`) |
| `ha_token` | A long-lived Home Assistant access token |
| `debug` | Enable verbose logging for troubleshooting |

There is no config field for the app's own HA account — that's learned
automatically (see the Event Schema section above).

### Start

Hit **Start** and check the **Log** tab. You should see:
```
[Firestore] Initialized. Hub path: smash_db/AA:BB:CC:DD:EE:FF/ha_events
[Startup] Discovery sequence complete.
Successfully authenticated with Home Assistant WebSocket
```

---

## BigQuery Setup (one-time)

### 1. Configure the Firebase → BigQuery extension for `ha_events`

In Firebase Console → Extensions → **Stream Firestore to BigQuery** → Reconfigure (or install a second instance), set the collection group to `ha_events` and the BigQuery table ID to `ha_logs` (this produces `ha_logs_raw_changelog` / `ha_logs_raw_latest`).

### 2. Create the flattened view

Run once in BigQuery (last updated 2026-07-09 — includes the Hub Logging Spec fields):

```sql
CREATE OR REPLACE VIEW `schnell-home-automation.schnell_analytics.ha_logs` AS
SELECT
  JSON_VALUE(data, '$.hub_id')                                    AS hub_id,
  JSON_VALUE(data, '$.event_id')                                  AS event_id,
  JSON_VALUE(data, '$.timestamp')                                 AS event_timestamp,
  JSON_VALUE(data, '$.date')                                      AS date,
  JSON_VALUE(data, '$.time')                                      AS time,
  SAFE_CAST(JSON_VALUE(data, '$.hour') AS INT64)                  AS hour,
  JSON_VALUE(data, '$.day_of_week')                               AS day_of_week,
  JSON_VALUE(data, '$.log_source')                                AS log_source,
  JSON_VALUE(data, '$.use_case')                                  AS use_case,
  JSON_VALUE(data, '$.ha_event_type')                             AS ha_event_type,
  JSON_VALUE(data, '$.entity_id')                                 AS entity_id,
  JSON_VALUE(data, '$.action')                                    AS action,
  JSON_VALUE(data, '$.old_state')                                 AS old_state,
  JSON_VALUE(data, '$.new_state')                                 AS new_state,
  JSON_VALUE(data, '$.room')                                      AS room,
  JSON_VALUE(data, '$.floor')                                     AS floor,
  JSON_VALUE(data, '$.device_type')                               AS device_type,
  JSON_VALUE(data, '$.origin')                                    AS origin,
  JSON_VALUE(data, '$.context_id')                                AS context_id,
  JSON_VALUE(data, '$.context_user_id')                           AS context_user_id,
  JSON_VALUE(data, '$.docklet_id')                                AS docklet_id,
  JSON_VALUE(data, '$.dock_id')                                   AS dock_id,
  JSON_VALUE(data, '$.docklet_state_change_ts')                   AS docklet_state_change_ts,
  JSON_VALUE(data, '$.matter_command_ts')                         AS matter_command_ts,
  JSON_VALUE(data, '$.snap_state_change_ts')                      AS snap_state_change_ts,
  SAFE_CAST(JSON_VALUE(data, '$.ha_processing_latency_ms') AS INT64) AS ha_processing_latency_ms,
  JSON_VALUE(data, '$.thread_node_id')                            AS thread_node_id,
  JSON_VALUE(data, '$.network_type')                              AS network_type,
  JSON_VALUE(data, '$.actuation_source')                          AS actuation_source,
  JSON_VALUE(data, '$.trigger_id')                                AS trigger_id,
  SAFE_CAST(JSON_VALUE(data, '$.is_trigger') AS BOOL)             AS is_trigger
FROM `schnell-home-automation.schnell_analytics.ha_logs_raw_latest`
WHERE data IS NOT NULL;
```

Full detail on the last three columns lives in
`../Analytics/docs/HA_TELEMETRY.md` §3a.

Query it:
```sql
SELECT * FROM `schnell-home-automation.schnell_analytics.ha_logs`
ORDER BY event_timestamp DESC
LIMIT 200;
```

---

## Noise Filtering

The following are automatically dropped and never written to Firestore:

- **Event types:** `time_changed`, `themes_updated`, `component_loaded`, `core_config_updated`, recorder statistics events
- **Domains:** `device_tracker`, `upnp`, `sun`, `zone`, `weather`
- **Entity prefixes:** router sensors, network sensors, wifi sensors, ping, bandwidth, uptime entities
- **Rapid duplicates:** identical state changes within 500ms on the same entity are deduplicated
