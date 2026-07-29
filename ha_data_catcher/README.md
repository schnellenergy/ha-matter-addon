# HA Data Catcher — Analytics Collector

![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-03A9F4?style=flat-square&logo=home-assistant)
![Platform](https://img.shields.io/badge/Platform-Multi--Arch-E91E63?style=flat-square)
![Version](https://img.shields.io/badge/Version-1.0.0-4CAF50?style=flat-square)

Real-time telemetry pipeline for the **Schnell Home Automation** platform.
Captures Matter device node details, enriches them with room/floor/dock/snap metadata,
reads custom cluster attributes from each endpoint, and syncs the results to
**Google Sheets** and **Firestore** — making hardware-level analytics available to the team
without touching the firmware.

---

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Data Sources](#data-sources)
3. [API Endpoints Reference](#api-endpoints-reference)
4. [How Node Details Are Fetched](#how-node-details-are-fetched)
5. [How Endpoints 1–6 Are Scanned](#how-endpoints-16-are-scanned)
6. [How Custom Cluster Attributes Are Read](#how-custom-cluster-attributes-are-read)
7. [How Metadata Enrichment Works](#how-metadata-enrichment-works)
8. [Google Sheets Output Schema](#google-sheets-output-schema)
9. [Complete Data Flow — Step by Step](#complete-data-flow--step-by-step)
10. [Event Schema (Firestore)](#event-schema-firestore)
11. [Installation & Configuration](#installation--configuration)
12. [Directory Structure](#directory-structure)
13. [Troubleshooting](#troubleshooting)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HOME ASSISTANT OS                                  │
│                                                                             │
│   ┌──────────────┐    ┌───────────────────┐    ┌────────────────────────┐   │
│   │  Matter       │    │  Custom Data       │    │  Home Assistant        │   │
│   │  Server       │    │  Storage Add-on    │    │  Core                  │   │
│   │  (port 5580)  │    │  (port 8100)       │    │  (port 8123)           │   │
│   │               │    │                    │    │                        │   │
│   │  WebSocket    │    │  REST API          │    │  WebSocket             │   │
│   │  /ws          │    │  /api/data/...     │    │  /api/websocket        │   │
│   └───────┬───────┘    └────────┬───────────┘    └───────────┬────────────┘   │
│           │                     │                            │               │
│           │         ┌───────────┴────────────────────────────┘               │
│           │         │                                                        │
│   ┌───────┴─────────┴─────────────────────────────────────────────────────┐  │
│   │                    HA DATA CATCHER ADD-ON                              │  │
│   │                                                                       │  │
│   │   ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────┐  │  │
│   │   │ AnalyticsCollector│  │ CustomStorage     │  │ WebSocket          │  │  │
│   │   │                  │  │ Collector          │  │ Collector          │  │  │
│   │   │ • Fetch nodes    │  │ • Poll every 30s   │  │ • Real-time events │  │  │
│   │   │ • Read attrs     │  │ • Docks metadata   │  │ • State changes    │  │  │
│   │   │ • Match metadata │  │ • Snaps metadata   │  │ • Call service     │  │  │
│   │   │ • Build rows     │  │ • Room/Floor map   │  │ • Automations      │  │  │
│   │   └────────┬─────────┘  └──────────────────┘  └──────────┬───────────┘  │  │
│   │            │                                             │              │  │
│   │            ▼                                             ▼              │  │
│   │   ┌────────────────┐                          ┌──────────────────────┐  │  │
│   │   │ Google Sheets   │                          │ Firestore Writer     │  │  │
│   │   │ (Webhook POST)  │                          │ smash_db/<hub>/...   │  │  │
│   │   └────────────────┘                          └──────────────────────┘  │  │
│   └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                    │                                       │
                    ▼                                       ▼
           ┌────────────────┐                     ┌──────────────────┐
           │  Google Sheets  │                     │  BigQuery         │
           │  "node details" │                     │  (via Firestore   │
           │  "Master_History│                     │   extension)      │
           └────────────────┘                     └──────────────────┘
```

---

## Data Sources

The Analytics Collector pulls data from **three independent sources** and merges them into a single unified output:

| Source | Protocol | What It Provides |
|---|---|---|
| **Matter Server** (`ws://core-matter-server:5580/ws`) | WebSocket (JSON-RPC) | Every commissioned node's raw attributes, including endpoints 1–6 and custom cluster data |
| **Custom Data Storage** (`http://homeassistant:8100`) | REST API | Dock/Snap metadata — device names, room assignments, docklet bindings, snap sub-device labels |
| **Home Assistant Core** (`ws://homeassistant:8123/api/websocket`) | WebSocket | Real-time event stream (state changes, service calls), device & entity registries |

---

## API Endpoints Reference

Below is every endpoint this add-on connects to. All endpoints are internal to Home Assistant OS unless noted otherwise.

### Quick Reference — All Endpoints at a Glance

| Type | Method | Endpoint URL | Purpose |
|------|--------|-------------|---------|
| **REST** | `GET` | `http://homeassistant:8100/api/data/device_setup` | Fetch dock & snap metadata |
| **REST** | `GET` | `http://homeassistant:8100/api/data/home_setup` | Fetch room & floor names |
| **REST** | `GET` | `http://homeassistant:8100/api/data/app_identity` | Fetch Flutter app's HA user ID |
| **REST** | `POST` | `<google_webhook_url>` *(external)* | Push node rows to Google Sheets |
| **WebSocket** | `connect` | `ws://core-matter-server:5580/ws` | Fetch Matter nodes + attributes |
| **WebSocket** | `connect` | `ws://homeassistant:8123/api/websocket` | Real-time HA events + registries |
| **Firestore** | `write` | `smash_db/<hub_mac>/ha_events/<event_id>` | Store enriched HA events |

---

### Detailed Breakdown

### Matter Server WebSocket (`ws://core-matter-server:5580/ws`)

| Command | Direction | Purpose | Used By |
|---|---|---|---|
| *(initial connection)* | ← Server | Receives a welcome/info JSON frame containing `fabric_id`, `compressed_fabric_id`, `server_version` | `analytics_collector.py` |
| `{"message_id": 1, "command": "get_nodes"}` | → Server | Requests the full list of commissioned Matter nodes with all their attributes | `analytics_collector.py` |
| *(response)* `{"message_id": 1, "result": [...]}` | ← Server | Returns an array of node objects, each with `node_id`, `date_commissioned`, and a flat `attributes` dict using `<endpoint>/<cluster_id>/<attribute_id>` keys | `analytics_collector.py` |

**Attribute key format inside each node:**

| Key Pattern | Example | What It Reads |
|---|---|---|
| `{ep}/6/0` | `1/6/0` | On/Off cluster — endpoint 1 on/off state |
| `{ep}/30/0` | `1/30/0` | Binding cluster — used to detect if endpoint is bound |
| `{ep}/320765697/2` | `1/320765697/2` | Custom Cluster `0x130AFF01`, Attribute 2 |
| `{ep}/320765697/3` | `1/320765697/3` | Custom Cluster `0x130AFF01`, Attribute 3 |
| `{ep}/320765697/4` | `1/320765697/4` | Custom Cluster `0x130AFF01`, Attribute 4 |
| `{ep}/320765697/5` | `1/320765697/5` | Custom Cluster `0x130AFF01`, Attribute 5 |

---

### Custom Data Storage REST API (`http://homeassistant:8100`)

| Method | Endpoint | Purpose | Used By |
|---|---|---|---|
| `GET` | `/api/data/device_setup` | Fetches all dock and snap metadata — names, `matter_node_id`, `room_id`, docklets, sub_devices | `analytics_collector.py`, `custom_storage_collector.py` |
| `GET` | `/api/data/home_setup` | Fetches home structure — floors and rooms with their IDs and names | `analytics_collector.py`, `custom_storage_collector.py`, `supervisor.py` |
| `GET` | `/api/data/app_identity` | Fetches the Flutter app's HA user ID for origin classification | `custom_storage_collector.py` |

**Response nesting (critical!):**

All three endpoints return data nested inside `data.structure`:

```
Response JSON
  └── "data"
       └── "structure"
            ├── "docks": { ... }      ← device_setup
            ├── "snaps": { ... }      ← device_setup
            └── "floors": [ ... ]     ← home_setup
```

The collector handles both direct and nested formats for backwards compatibility:

```python
val = body.get("value") or body.get("data") or body
struct = val.get("structure") if isinstance(val, dict) and "structure" in val else val
```

---

### Home Assistant Core WebSocket (`ws://homeassistant:8123/api/websocket`)

| Step | Message Type | Payload | Purpose | Used By |
|---|---|---|---|---|
| 1 | ← `auth_required` | `{"type": "auth_required"}` | Server requests authentication | `websocket_collector.py` |
| 2 | → `auth` | `{"type": "auth", "access_token": "<token>"}` | Client sends credentials | `websocket_collector.py` |
| 3 | ← `auth_ok` | `{"type": "auth_ok"}` | Authentication confirmed | `websocket_collector.py` |
| 4 | → Registry fetch | `{"id": N, "type": "config/floor_registry/list"}` | Fetch all floors | `websocket_collector.py` |
| 5 | → Registry fetch | `{"id": N, "type": "config/area_registry/list"}` | Fetch all areas/rooms | `websocket_collector.py` |
| 6 | → Registry fetch | `{"id": N, "type": "config/device_registry/list"}` | Fetch all devices (34 devices cached) | `websocket_collector.py` |
| 7 | → Registry fetch | `{"id": N, "type": "config/entity_registry/list"}` | Fetch all entities (976 entities cached) | `websocket_collector.py` |
| 8 | → Subscribe | `{"id": N, "type": "subscribe_events"}` | Subscribe to ALL HA events | `websocket_collector.py` |
| 9 | ← Events | `{"type": "event", "event": {...}}` | Continuous stream of `state_changed`, `call_service`, `automation_triggered`, etc. | `websocket_collector.py` |

**Auto-refresh:** When the collector receives `device_registry_updated`, `entity_registry_updated`, or `area_registry_updated` events, it automatically re-fetches the registries (steps 4–7) to keep the cache fresh.

---

### Google Sheets Webhook (External)

| Method | URL | Payload | Purpose | Used By |
|---|---|---|---|---|
| `POST` | `<google_webhook_url>` (configured in add-on options) | `{"rows": [[col1, col2, ...], ...]}` | Pushes node endpoint rows to Google Sheets | `analytics_collector.py` |

The Google Apps Script `doPost(e)` function receives this payload and writes to:
- **`node details`** tab (auto-created with headers if missing)
- **`Master_History`** tab (backup copy)

---

### Firestore Write Paths

| Collection Path | Document ID | Purpose | Used By |
|---|---|---|---|
| `smash_db/<hub_mac>/ha_events` | `<event_id>` (UUID) | Stores enriched real-time HA events | `firestore_writer.py` |

From Firestore, the **Stream Firestore to BigQuery** extension syncs to:
- `schnell_analytics.ha_logs_raw_changelog` (raw table)
- `schnell_analytics.ha_logs_raw_latest` (latest view)
- `schnell_analytics.ha_logs` (flattened view)

---

### Step 1 — Connect to the Matter Server WebSocket

The Analytics Collector opens a direct WebSocket connection to the **Matter Server add-on** running inside Home Assistant:

```python
async with websockets.connect("ws://core-matter-server:5580/ws") as websocket:
    await websocket.send(json.dumps({"message_id": 1, "command": "get_nodes"}))
```

### Step 2 — Skip the Welcome Message

When the WebSocket first connects, the Matter Server sends a **welcome/info message** (containing fabric ID, server version, etc.) *before* it sends the actual nodes response. The collector loops to skip this:

```python
for _ in range(5):
    response = await websocket.recv()
    data = json.loads(response)
    if data.get("message_id") == 1 and "result" in data:
        return data["result"]  # ← This is the nodes array
```

> **Why range(5)?** — The Matter Server may emit up to 2–3 informational frames before the response. Five iterations provides a safe margin while preventing infinite loops.

### Step 3 — What You Get Back

The `get_nodes` response is a JSON array. Each element represents one commissioned Matter node:

```json
{
  "node_id": 105,
  "date_commissioned": "2026-07-24T05:30:00",
  "attributes": {
    "1/6/0":   true,          // Endpoint 1, Cluster 6 (On/Off), Attribute 0 (OnOff state)
    "1/30/0":  [...],         // Endpoint 1, Cluster 30 (Binding), Attribute 0 (Binding list)
    "2/6/0":   false,
    "1/320765697/2": 42,      // Endpoint 1, Custom Cluster 0x130AFF01, Attribute 2
    "1/320765697/3": 100,     // Endpoint 1, Custom Cluster 0x130AFF01, Attribute 3
    ...
  }
}
```

The `attributes` dictionary uses the **Matter path convention**: `<endpoint>/<cluster_id>/<attribute_id>`.

---

## How Endpoints 1–6 Are Scanned

Every Schnell dock and snap physically has **6 endpoints** (positions/channels). The collector iterates over endpoints 1 through 6 for each node:

```python
for ep in range(1, 7):  # Endpoints 1, 2, 3, 4, 5, 6
    # Read custom cluster attributes for this endpoint
    attr_2 = attributes.get(f"{ep}/{CUSTOM_CLUSTER_ID}/2", 0)
    attr_3 = attributes.get(f"{ep}/{CUSTOM_CLUSTER_ID}/3", 0)
    attr_4 = attributes.get(f"{ep}/{CUSTOM_CLUSTER_ID}/4", 0)
    attr_5 = attributes.get(f"{ep}/{CUSTOM_CLUSTER_ID}/5", 0)

    # Check if this endpoint has a Binding cluster (Cluster 30)
    is_bound = any(k.startswith(f"{ep}/30/") for k in attributes.keys())
```

This generates **6 rows per node** — one row per endpoint. A dock with node ID 109 produces:

| Node ID | Endpoint | Attr 2 | Attr 3 | Attr 4 | Attr 5 | Is Bound? |
|---------|----------|--------|--------|--------|--------|-----------|
| node_109 | endpoint_1 | 42 | 100 | 0 | 0 | TRUE |
| node_109 | endpoint_2 | 0 | 0 | 0 | 0 | FALSE |
| node_109 | endpoint_3 | 15 | 80 | 0 | 0 | TRUE |
| node_109 | endpoint_4 | 0 | 0 | 0 | 0 | FALSE |
| node_109 | endpoint_5 | 0 | 0 | 0 | 0 | FALSE |
| node_109 | endpoint_6 | 0 | 0 | 0 | 0 | FALSE |

---

## How Custom Cluster Attributes Are Read

### The Custom Cluster

Schnell hardware defines a **vendor-specific Matter cluster** for proprietary telemetry:

| Property | Value |
|---|---|
| **Cluster ID** | `0x130AFF01` (decimal: `320765697`) |
| **Attribute 2** (`0x0002`) | Hardware-defined metric (e.g., current load, press count) |
| **Attribute 3** (`0x0003`) | Hardware-defined metric |
| **Attribute 4** (`0x0004`) | Hardware-defined metric |
| **Attribute 5** (`0x0005`) | Hardware-defined metric |

### How Attributes Are Accessed

The Matter Server flattens every attribute into a dot-path key inside the node's `attributes` dictionary. The collector reads them using this pattern:

```python
CUSTOM_CLUSTER_ID = 0x130AFF01  # = 320765697

def get_attr(attr_id):
    return attributes.get(f"{ep}/{CUSTOM_CLUSTER_ID}/{attr_id}", 0)

# For endpoint 3, attribute 5:
# Key = "3/320765697/5"
# Returns the value, or 0 if not present
```

### Binding Detection

To determine whether an endpoint is **bound** to another device (e.g., a snap controlling a dock), the collector checks for the presence of the **Binding cluster (Cluster ID 30)**:

```python
is_bound = any(k.startswith(f"{ep}/30/") for k in attributes.keys())
# If endpoint 1 has "1/30/0" in attributes → is_bound = TRUE
```

---

## How Metadata Enrichment Works

Raw Matter data only contains numeric node IDs and attribute values. The collector enriches this with human-readable names by cross-referencing two APIs:

### Source 1: `device_setup` (Dock & Snap Metadata)

```
GET http://homeassistant:8100/api/data/device_setup
```

Response structure:

```json
{
  "data": {
    "structure": {
      "docks": {
        "dock_abc123": {
          "name": "Bedroom Dock",
          "matter_node_id": "109",
          "room_id": "room_1",
          "docklets": {
            "docklet_1": {
              "position": 1,
              "entity_id": "light.bedroom_light",
              "bound_device_label": "Bedroom Light",
              "bound_device_entity_id": "light.bedroom_light"
            },
            ...
          }
        }
      },
      "snaps": {
        "board_17852401_module_1": {
          "label": "3X SUPER SNAP-1",
          "matter_node_id": "105",
          "room_id": "room_2",
          "sub_devices": [
            { "endpoint_id": 1, "name": "Supersnap Light 6", "entity_id": "light.supersnap_light_6" },
            ...
          ]
        }
      }
    }
  }
}
```

### Source 2: `home_setup` (Room & Floor Names)

```
GET http://homeassistant:8100/api/data/home_setup
```

Response structure:

```json
{
  "data": {
    "structure": {
      "floors": [
        {
          "name": "Basement",
          "rooms": [
            { "room_id": "room_2", "name": "Balcony" },
            { "room_id": "room_1", "name": "Bedroom" }
          ]
        }
      ]
    }
  }
}
```

### The Matching Algorithm

For each Matter node, the collector attempts to match it against both the `docks` and `snaps` maps:

```
For each node from Matter Server:
  1. Extract node_id (e.g., 105)
  2. Build entity_id string: "node_105"

  3. Search DOCKS:
     → Compare node_id with dock.matter_node_id
     → Compare entity_id with dock.entity_id
     → If match found → device_type = "dock"

  4. If no dock match, search SNAPS:
     → Compare node_id with snap.matter_node_id
     → Compare entity_id with snap.entity_id
     → If match found → device_type = snap.type (e.g., "3X SUPER SNAP-1")

  5. Resolve room & floor:
     → Use matched device's room_id → look up room_map → get room name & floor name

  6. For each endpoint (1–6):
     → Match docklet by position (docks) or sub_device by endpoint_id (snaps)
     → Extract docklet_label, bound_device_label, bound_device_entity_id
```

### What Happens When a Node Is NOT Matched

If a node is not found in either docks or snaps, it falls back to:

| Field | Fallback Value |
|---|---|
| Device Type | `matter_node` |
| Dock/Snap ID | *(empty)* |
| Node Label | *(empty)* |
| Room / Floor | *(empty)* |
| Docklet Labels | *(empty)* |

This typically means the device was commissioned but the Flutter app's save operation failed (e.g., due to the Node ID extraction bug).

---

## Google Sheets Output Schema

The Analytics Collector builds a 2D array of rows and pushes them to a Google Apps Script Web App via HTTP POST. Each row contains **18 columns**:

| Column | Field | Example | Source |
|--------|-------|---------|--------|
| A | **Timestamp** | `2026-07-29 7:54:21` | System clock |
| B | **Hub MAC** | `2C:CF:67:6E:11:52` | HA Supervisor / config |
| C | **Node ID** | `node_105` | Matter Server |
| D | **Module Type** | `3X SUPER SNAP-1` | Custom Storage |
| E | **Dock/Snap ID** | `board_17852401_module_1` | Custom Storage |
| F | **Dock Name** | `3X SUPER SNAP-1` | Custom Storage |
| G | **Room Name** | `Balcony` | Custom Storage (home_setup) |
| H | **Floor Name** | `Basement` | Custom Storage (home_setup) |
| I | **Endpoint** | `endpoint_1` | Computed (loop 1–6) |
| J | **Docklet ID** | `light.supersnap_light_6` | Custom Storage |
| K | **Docklet Label** | `Supersnap Light 6` | Custom Storage |
| L | **Bound Label** | `Supersnap Light 6` | Custom Storage |
| M | **Bound Entity ID** | `light.supersnap_light_6` | Custom Storage |
| N | **Is Bound?** | `TRUE` / `FALSE` | Matter Server (Cluster 30) |
| O | **Attr 2** | `42` | Matter Server (Custom Cluster) |
| P | **Attr 3** | `100` | Matter Server (Custom Cluster) |
| Q | **Attr 4** | `0` | Matter Server (Custom Cluster) |
| R | **Attr 5** | `0` | Matter Server (Custom Cluster) |

### Google Apps Script Destination

The webhook pushes to a Google Apps Script `doPost(e)` function that writes to two sheets:

| Sheet Tab | Purpose |
|---|---|
| **node details** | Primary analytics sheet — auto-created with headers on first push |
| **Master_History** | Backup/archive copy of all synced rows |

### Sync Schedule

The analytics sync runs **once on add-on startup**, then repeats every **24 hours**. To force a fresh sync, restart the add-on.

---

## Complete Data Flow — Step by Step

Here is the exact sequence when the Analytics Collector executes `run_sync()`:

```
 1. CONNECT to Matter Server WebSocket (ws://core-matter-server:5580/ws)
         │
 2. SEND  {"message_id": 1, "command": "get_nodes"}
         │
 3. RECEIVE  Skip welcome message, wait for message_id=1 response
         │
 4. PARSE  Extract array of nodes, each with node_id + attributes dict
         │
 5. FETCH  GET /api/data/device_setup → Parse docks, snaps from data.structure
         │
 6. FETCH  GET /api/data/home_setup → Parse floors[].rooms[] → build room_map
         │
 7. FOR EACH NODE:
    │
    ├─ 7a. Match node_id against docks (by matter_node_id or entity_id)
    ├─ 7b. If no dock match → match against snaps
    ├─ 7c. Resolve room_name and floor_name from room_map
    │
    └─ 7d. FOR EACH ENDPOINT (1–6):
           │
           ├─ Read custom cluster attributes: {ep}/320765697/2 through /5
           ├─ Check binding: any key starting with {ep}/30/
           ├─ Match docklet (dock) or sub_device (snap) by position
           └─ Build row → append to rows_array
         │
 8. POST  rows_array to Google Sheets Webhook
         │
 9. LOG   "Successfully synced N node endpoint rows to Google Sheets."
```

---

## Event Schema (Firestore)

In addition to the Google Sheets sync, the add-on also captures **real-time HA events** and writes them to Firestore. Every document written to `smash_db/<hub_mac>/ha_events/<event_id>` contains:

| Field | Description |
|---|---|
| `hub_id` | Hub MAC address |
| `event_id` | UUID — document ID and join key |
| `timestamp` | ISO-8601 event timestamp (hub-local timezone) |
| `date`, `time`, `hour`, `day_of_week` | Analytics-friendly time splits |
| `log_source` | True origin — `app:command`, `ha_ui:command`, `automation:<id>`, `scene:<id>`, or hardware fallback |
| `actuation_source` | Which hardware physically carried out the action |
| `trigger_id` | HA context ID, shared by every row a single action produces |
| `is_trigger` | `true` on the initiating row per action, `false` on fan-out rows |
| `entity_id` | Entity that changed |
| `action` | `turn_on`, `turn_off`, `state_transition`, etc. |
| `old_state`, `new_state` | State before and after the change |
| `room`, `floor` | Resolved from Custom Data Storage |
| `device_type` | Resolved load type (`Light`, `Fan`, `docklet`, …) |
| `docklet_id` | Docklet entity ID (dock events only) |
| `dock_id` | Dock hardware this entity is mapped to |
| `ha_processing_latency_ms` | `snap_state_change_ts − event_timestamp`, in milliseconds |

---

## Installation & Configuration

### 1. Install

1. Copy this folder into your Home Assistant `/addons/local/` directory (e.g. via the Samba share add-on).
2. In Home Assistant, go to **Settings → Add-ons → Add-on Store → ⋮ → Check for updates**.
3. Find **HA Data Catcher** under *Local add-ons* and click **Install**.
4. Configure the options below, then click **Start**.

### 2. Configure

| Option | Default | Description |
|---|---|---|
| `hub_id` | *(auto-discovered)* | The hub's MAC address (e.g. `AA:BB:CC:DD:EE:FF`). Leave empty to auto-discover. |
| `custom_storage_url` | `http://homeassistant:8100` | Base URL of the Custom Data Storage add-on. |
| `google_webhook_url` | *(empty)* | Your Google Apps Script Web App URL for Sheets sync. |
| `ha_token` | *(empty)* | Long-lived HA access token. Only needed outside Supervisor. |
| `debug` | `false` | Enable verbose logging. |

### 3. Google Sheets Setup

1. Create a Google Sheet (e.g., "Node details").
2. Go to **Extensions → Apps Script**.
3. Paste the `doPost()` function (see `google_apps_script.js` in this repo).
4. Deploy as **Web App** (Execute as Me, Anyone has access).
5. Copy the Web App URL into the add-on's `google_webhook_url` configuration.

### 4. Verify Startup

Open the add-on's **Log** tab. A healthy start looks like:

```
[Firestore] Initialized. Hub path: smash_db/AA:BB:CC:DD:EE:FF/ha_events
[Startup] Discovery sequence complete.
Successfully authenticated with Home Assistant WebSocket
Starting Matter Server analytics sync...
Successfully synced 24 node endpoint rows to Google Sheets.
```

---

## Directory Structure

```
ha_data_catcher/
├── app/
│   ├── main.py                          # Orchestrator — wires all components, runs event loop
│   ├── startup.py                       # Discovery: HA connection details, timezone, hub_id
│   ├── supervisor.py                    # HA Supervisor API client
│   ├── config_manager.py               # Loads options.json / environment variables
│   ├── logger.py                        # Shared logger
│   ├── collectors/
│   │   ├── analytics_collector.py      # ★ Core: Matter WS → metadata match → Google Sheets
│   │   ├── websocket_collector.py      # Persistent WebSocket connection + HA registry fetch
│   │   └── custom_storage_collector.py # Polls Custom Data Storage every 30 s
│   ├── processors/
│   │   ├── event_parser.py             # Raw HA event → structured record + event_id
│   │   ├── event_enricher.py           # Room/floor/device-type + origin classification
│   │   ├── metrics_fields.py           # Latency and Matter/Thread timing metrics
│   │   └── filters.py                  # Noise filtering (weather, network sensors, etc.)
│   └── firebase/
│       └── firestore_writer.py         # Firestore batch writer
├── Dockerfile                           # Container build (Python 3.11-slim)
├── build.yaml                           # HA build configuration
├── config.json                          # HA add-on manifest (options, ports, permissions)
├── requirements.txt                     # Python dependencies
├── run.sh                               # Entrypoint script
└── README.md                            # ← You are here
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| **"No nodes found, skipping Google Sheets push"** | WebSocket received the welcome message but missed the actual nodes response | Ensure the `for _ in range(5)` loop is in `fetch_matter_nodes()` |
| **Node shows as `matter_node` (no name)** | Flutter app failed to save the dock/snap to Custom Storage | Re-commission the device using the Flutter app (v1.0.8+ with `parts.last` fix) |
| **Endpoint columns all show `0`** | The custom cluster attributes are not present on the node | Verify firmware has the custom cluster (`0x130AFF01`) enabled |
| **Google Sheet is empty** | Webhook URL not configured, or Apps Script not deployed as new version | Check `google_webhook_url` in add-on config; redeploy Apps Script |
| **Events missing room/floor** | Custom Data Storage not reachable, or home setup not synced from app | Verify `http://homeassistant:8100/api/data/home_setup` returns data |
| **WebSocket keeps reconnecting** | HA Core not running | Check HA Core health; the add-on auto-retries every 5 seconds |

Enable the `debug` option for verbose per-event logging.

---

## Key Design Decisions

1. **Direct Matter WebSocket** — We connect directly to the Matter Server's WebSocket (`port 5580`) instead of going through HA's entity layer. This gives us raw access to custom cluster attributes that HA doesn't expose as entities.

2. **Metadata merge, not duplication** — Device names, rooms, and docklet bindings live in Custom Data Storage (managed by the Flutter app). The collector reads them at sync time rather than duplicating them.

3. **6 rows per node** — Even if some endpoints are unused, we always emit 6 rows. This keeps the sheet structure predictable and makes it easy to pivot/filter in Sheets or BigQuery.

4. **24-hour sync cycle** — The analytics sync runs once on startup, then every 24 hours. For real-time data, the Firestore event stream runs continuously in parallel.
