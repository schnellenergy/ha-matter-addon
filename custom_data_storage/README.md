# Custom Data Storage

A Home Assistant add-on that provides a **SQLite-backed REST API and WebSocket server** for storing structured JSON data used by the Schnell Home Automation app. It runs on port 8100 alongside Home Assistant (port 8123).

---

## What It Does

Home Assistant has no built-in way to persist custom app data — room names, device labels, UI preferences, scenes. This add-on fills that gap with a lightweight embedded database that the mobile app reads and writes directly.

The mobile app stores everything in three JSON objects:

| Category | Key | Contents |
|---|---|---|
| `home_automation` | `home_setup` | Floors, rooms, boxes (physical structure) |
| `home_automation` | `device_setup` | SNAPs, docks, Matter nodes with labels and icons |
| `home_automation` | `configurations` | Dashboard preferences, scenes, UI settings |

---

## Installation

1. Copy the `custom_data_storage` folder to your Home Assistant local add-ons path via Samba:
   ```
   \\homeassistant.local\addons\local\custom_data_storage
   ```

2. SSH into Home Assistant and run the diagnostic to verify the files are in order:
   ```bash
   cd /addons/local/custom_data_storage
   chmod +x diagnose_addon.sh fix_installation.sh
   ./diagnose_addon.sh
   ```

3. In the HA UI: **Settings → Add-ons → ⋮ (top right) → Reload**

4. Find **Custom Data Storage** in the Local add-ons section → **Install → Start**

---

## Configuration

Open the add-on's **Configuration** tab and set these options before starting:

| Option | Default | Description |
|---|---|---|
| `log_level` | `info` | Verbosity: `trace` `debug` `info` `warning` `error` `fatal` |
| `storage_path` | `/data/custom_storage` | Where the SQLite database lives (must be under `/data/`) |
| `max_storage_size_mb` | `2000` | Storage cap in MB |
| `enable_websocket` | `true` | Real-time sync across devices |
| `enable_cors` | `true` | Required for mobile app access |
| `api_key` | *(empty)* | Optional auth header for all data endpoints |
| `secure_ha_token` | *(empty)* | **Your Home Assistant long-lived access token** |

### Setting up `secure_ha_token` (required)

The mobile app fetches its HA authentication token from this add-on at setup time, so the token never needs to be hardcoded in the app binary.

1. In HA: **Profile → Long-Lived Access Tokens → Create Token**
2. Copy the generated token
3. Open this add-on → **Configuration** tab
4. Paste the token into the `secure_ha_token` field
5. **Save** and restart the add-on

The app will call `GET http://{hub-ip}:8100/api/ha-token` during WiFi setup and store the token in device secure storage automatically.

---

## API Reference

**Base URL:** `http://{hub-ip}:8100`

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Health check + storage stats |
| `GET` | `/api/ha-token` | Returns the configured HA token (used by mobile app during setup) |
| `POST` | `/api/data` | Store or overwrite a value |
| `GET` | `/api/data/{category}/{key}` | Read a specific value |
| `GET` | `/api/data/{category}` | Read all keys in a category |
| `GET` | `/api/data` | Read everything |
| `DELETE` | `/api/data/{category}/{key}` | Delete a value |
| `GET` | `/api/search?q={term}&category={cat}` | Full-text search |
| `GET` | `/api/categories` | List all categories |
| `GET` | `/api/metadata` | DB stats (size, counts, categories) |
| `POST` | `/api/optimize` | Run SQLite VACUUM |
| `POST` | `/api/backup` | Backup the database file |

### Store data
```bash
curl -X POST http://homeassistant.local:8100/api/data \
  -H "Content-Type: application/json" \
  -d '{"category": "home_automation", "key": "home_setup", "value": {...}}'
```

### Read data
```bash
curl http://homeassistant.local:8100/api/data/home_automation/home_setup
```

### Health check
```bash
curl http://homeassistant.local:8100/health
```

---

## WebSocket Events

Connect to `http://{hub-ip}:8100` with a Socket.IO client.

| Event | Direction | Payload |
|---|---|---|
| `connected` | Server → Client | `{ storage_type: "sqlite" }` |
| `data_updated` | Server → All clients | `{ action, category, key, value, timestamp }` |
| `get_data` | Client → Server | `{ category, key }` — request a value |
| `data_response` | Server → Client | Response to `get_data` |
| `error` | Server → Client | `{ message }` |

Every write (`POST /api/data`) and delete automatically broadcasts a `data_updated` event to all connected devices — no polling needed.

---

## Multi-Device Write Pattern

This API is **replace-only** — there is no PATCH. To update a single field safely across multiple devices:

```
1. GET   current JSON from hub
2. MODIFY the field locally
3. POST  the entire modified JSON back
4. WebSocket broadcasts the change to all other devices
```

Stamp each write with `_version` (increment) and `_last_updated_by` (device ID) inside your JSON to track concurrent edits.

---

## Troubleshooting

**Add-on not showing in Local add-ons:**
Run `./diagnose_addon.sh` — it checks file placement, permissions, and supervisor registration.

**Port 8100 not reachable:**
Confirm the add-on status is Running. Check add-on logs (**Log** tab) for startup errors.

**Token not returned by `/api/ha-token`:**
The `secure_ha_token` field is empty. Open Configuration tab, paste your token, Save, and restart.

**Data not persisting after restart:**
Verify `storage_path` is under `/data/`. Paths outside `/data/` are not persistent in HA add-ons.

**Enable debug logs:**
Set `log_level: debug` in Configuration and restart.

---

For full technical details — database schema, performance characteristics, deployment variants — see [ARCHITECTURE.md](ARCHITECTURE.md).
