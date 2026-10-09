# Custom Data Storage — Architecture

Technical reference for the Custom Data Storage Home Assistant add-on.

---

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Schnell Mobile App                     │
│                   (Flutter / Dart)                       │
└──────────┬──────────────────────────┬───────────────────┘
           │ HTTP REST                │ Socket.IO
           │ port 8100                │ port 8100
           ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│          Custom Data Storage Add-on (this)              │
│          Flask + Flask-SocketIO + SQLite                 │
│          /data/custom_storage/custom_data.db            │
└──────────────────────────────────────────────────────────┘

           Separate connection ↓
┌─────────────────────────────────────────────────────────┐
│              Home Assistant Core                         │
│              port 8123  (REST + WebSocket)               │
└──────────────────────────────────────────────────────────┘
```

The add-on and HA core are **independent services**. The mobile app connects to both — HA for device control (lights, fans, switches), this add-on for structured app data (room names, device labels, scenes, UI preferences).

---

## Add-on File Structure

```
custom_data_storage/
├── config.json          HA supervisor manifest
├── Dockerfile           Container image definition
├── run.sh               Startup script — sets env vars, launches main_fixed.py
├── diagnose_addon.sh    Diagnostic tool (checks placement, permissions, supervisor)
├── fix_installation.sh  Pre-deploy validator (permissions, slug match, required files)
├── app/
│   ├── main_fixed.py    Flask application — all REST endpoints and WebSocket handlers
│   └── database_storage.py  SQLite ORM layer — CRUD, search, backup, metadata
├── README.md            User-facing guide (installation, config, API reference)
└── ARCHITECTURE.md      This file
```

`run.sh` explicitly calls `python3 main_fixed.py`. There is only one active application version.

---

## Token Provisioning Flow

The add-on serves the HA long-lived access token to the mobile app so the token never needs to be hardcoded in the app binary.

```
User installs add-on
        ↓
User opens add-on Configuration tab in HA UI
        ↓
User pastes HA long-lived token into secure_ha_token field → Save
        ↓
run.sh exports SECURE_HA_TOKEN env var
        ↓
main_fixed.py reads it at startup
        ↓
App calls GET http://{hub-ip}:8100/api/ha-token during WiFi setup
        ↓
Add-on returns { "token": "eyJ..." }
        ↓
App stores token in device FlutterSecureStorage + Kotlin SharedPreferences
        ↓
All subsequent HA API calls use the stored token — no further addon calls needed
```

The `/api/ha-token` endpoint is accessible on LAN without authentication (same trust model as HA itself on port 8123). Token is masked (`password` type) in the HA config UI.

---

## Database Design

### Engine

| Property | Value |
|---|---|
| Database | SQLite 3.x |
| Mode | WAL (Write-Ahead Logging) — concurrent reads, serialised writes |
| Cache | 10 MB in-memory page cache |
| Temp storage | Memory (not disk) |
| Connection timeout | 30 seconds |
| ACID compliance | Full |

### Schema

```sql
CREATE TABLE custom_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT    NOT NULL,
    key         TEXT    NOT NULL,
    value       TEXT    NOT NULL,       -- JSON-encoded string
    value_type  TEXT    NOT NULL,       -- Python type name (dict, list, str, etc.)
    created_at  TEXT    NOT NULL,       -- ISO 8601 timestamp
    updated_at  TEXT    NOT NULL,       -- ISO 8601 timestamp
    UNIQUE(category, key)
);

CREATE TABLE metadata (
    id           INTEGER PRIMARY KEY,
    created_at   TEXT,
    last_updated TEXT,
    version      TEXT,
    total_ops    INTEGER DEFAULT 0
);

CREATE INDEX idx_category_key ON custom_data(category, key);  -- primary lookup
CREATE INDEX idx_category     ON custom_data(category);        -- category scan
CREATE INDEX idx_updated_at   ON custom_data(updated_at);      -- recency queries
```

All writes are atomic `INSERT OR REPLACE` (upsert). There is no partial update — the full JSON value is replaced on every write.

### Storage Path

```
/data/custom_storage/custom_data.db      Main database
/data/custom_storage/custom_data.db-wal  Write-Ahead Log (auto-managed)
/data/custom_storage/custom_data.db-shm  Shared memory file (auto-managed)
```

The `/data/` prefix is required for persistence across HA restarts. Paths outside `/data/` are ephemeral in HA add-ons.

### Performance

| Operation | Typical latency |
|---|---|
| Indexed read | < 1 ms |
| Write (upsert) | < 1 ms |
| Full-text search | < 10 ms |
| Concurrent readers | Unlimited |
| Concurrent writers | 1 (WAL queues additional writes) |

---

## 3-JSON Data Architecture

All Schnell app data lives in one category (`home_automation`) with three keys:

### `home_setup` — Physical structure

```json
{
  "_version": 1,
  "_last_updated_by": "device-uuid",
  "home_id": "home_1001",
  "name": "My Home",
  "timezone": "Asia/Kolkata",
  "location": { "latitude": 12.97, "longitude": 77.59, "address": "Bengaluru" },
  "hub_ip": "192.168.1.100",
  "floors": [
    {
      "floor_id": "floor_2001",
      "name": "Ground Floor",
      "level": 0,
      "rooms": [
        {
          "room_id": "room_3001",
          "name": "Living Room",
          "icon": "living_room",
          "boxes": [
            {
              "box_id": "box_4001",
              "name": "Main Switchboard",
              "snap_ids": ["snap_5001", "snap_5002"]
            }
          ]
        }
      ]
    }
  ]
}
```

### `device_setup` — Device details (flat map for O(1) lookup)

```json
{
  "_version": 1,
  "_last_updated_by": "device-uuid",
  "snaps": {
    "snap_5001": {
      "label": "Living Room Fan",
      "matter_node_id": "matter_node_aaa",
      "type": "dimmer",
      "room_id": "room_3001",
      "box_id": "box_4001",
      "custom_icon": "fan",
      "is_favorite": true
    }
  },
  "docks": {
    "dock_9001": {
      "label": "Living Remote",
      "matter_node_id": "matter_node_bbb",
      "room_id": "room_3001",
      "battery_level": 88
    }
  }
}
```

### `configurations` — UI state and scenes

```json
{
  "_version": 1,
  "_last_updated_by": "device-uuid",
  "shared_preferences": {
    "ui_theme": "dark",
    "layout_mode": "grid"
  },
  "dashboard": {
    "pinned_devices": ["snap_5001"],
    "quick_actions": ["scene_good_morning"]
  },
  "scenes": {
    "scene_good_morning": {
      "name": "Good Morning",
      "actions": [
        { "device_id": "snap_5001", "state": "on" }
      ]
    }
  }
}
```

---

## Multi-Device Write Safety

The API is **replace-only** (no PATCH). Multiple devices writing simultaneously use this pattern:

```
Device A                          Device B
   │                                 │
   ├── GET home_automation/device_setup
   │                                 ├── GET home_automation/device_setup
   ├── modify snap_5001.label        │
   ├── increment _version            ├── modify snap_5002.label
   ├── set _last_updated_by = A      ├── increment _version
   ├── POST full object              ├── set _last_updated_by = B
   │                                 ├── POST full object (wins if after A)
   │◄── WebSocket: data_updated ─────┤
```

Last write wins. The `_version` field and `_last_updated_by` field are for auditing and conflict detection in the app layer — the add-on itself does not enforce ordering.

---

## Configuration Reference

All options are set in the add-on Configuration tab and passed to the application as environment variables by `run.sh`.

| Option | Env var | Type | Default | Notes |
|---|---|---|---|---|
| `log_level` | `LOG_LEVEL` | enum | `info` | Controls Flask + app logging verbosity |
| `storage_path` | `STORAGE_PATH` | str | `/data/custom_storage` | Must be under `/data/` |
| `max_storage_size_mb` | `MAX_STORAGE_SIZE_MB` | int | `2000` | Soft cap — enforced at app layer, not OS |
| `enable_websocket` | `ENABLE_WEBSOCKET` | bool | `true` | Disabling reduces resource use if not needed |
| `enable_cors` | `ENABLE_CORS` | bool | `true` | Required for mobile app access |
| `api_key` | `API_KEY` | str | *(empty)* | If set, all `/api/*` endpoints require `X-API-Key` header or `?api_key=` param. `/api/ha-token` and `/health` are exempt. |
| `secure_ha_token` | `SECURE_HA_TOKEN` | password | *(empty)* | HA long-lived access token. Masked in UI. Served by `/api/ha-token`. |

---

## Deployment by HA Installation Type

| HA Install Type | Add-on Location | Reload Command |
|---|---|---|
| Home Assistant OS | `/addons/local/custom_data_storage/` | Settings → Add-ons → ⋮ → Reload |
| Home Assistant Supervised | `/usr/share/hassio/addons/local/custom_data_storage/` | `ha addons reload` via SSH |
| Home Assistant Container | Not supported (no Supervisor) | — |
| Home Assistant Core | Not supported (no Supervisor) | — |

**Recommended install method (all supported types):**

1. Enable the Samba share add-on in HA
2. Map `\\homeassistant.local\addons` on your computer
3. Copy the `custom_data_storage` folder into the `local` subfolder
4. SSH in and run `./diagnose_addon.sh` to verify
5. Reload the Supervisor from HA UI

---

## WebSocket Protocol

The server uses Flask-SocketIO with eventlet async mode.

**Connection:**
```
ws://  or  http://  {hub-ip}:8100
Transport: websocket (preferred) or polling (fallback)
```

**Server-emitted events:**

| Event | When | Payload fields |
|---|---|---|
| `connected` | On socket connect | `storage_type: "sqlite"` |
| `data_updated` | After every POST or DELETE | `action, category, key, value, timestamp` |
| `data_response` | Reply to `get_data` | `category, key, value, found` or `category, data` |
| `error` | On handler exception | `message` |

**Client-emitted events:**

| Event | Payload | Purpose |
|---|---|---|
| `get_data` | `{ category, key }` or `{ category }` | Request data without HTTP |

---

## Maintenance Operations

**Optimize (VACUUM + ANALYZE):**
```bash
curl -X POST http://homeassistant.local:8100/api/optimize
```
Reclaims space from deleted rows. Run after bulk deletes.

**Backup:**
```bash
curl -X POST http://homeassistant.local:8100/api/backup
# Creates: /data/custom_storage/backup_custom_data_{timestamp}.db
```

**Direct SQLite access via SSH:**
```bash
sqlite3 /data/custom_storage/custom_data.db
.tables
SELECT category, key, updated_at FROM custom_data;
.quit
```

**Reset all data (destructive):**
```bash
rm -rf /data/custom_storage/*
# Restart the add-on to recreate the database
```

---

## Diagnostic Tools

**`diagnose_addon.sh`** — Run after copying files, before installing in HA. Checks:
- No duplicate `config.json` at wrong level
- Required files present (`Dockerfile`, `run.sh`, `app/main_fixed.py`, `app/database_storage.py`)
- File permissions correct (`run.sh` is executable)
- Supervisor communication working
- Add-on is registered with supervisor

**`fix_installation.sh`** — Run if `diagnose_addon.sh` reports permission or structure errors. Fixes:
- Resets file permissions
- Validates folder slug matches `config.json` slug
- Checks YAML/JSON syntax of config files
