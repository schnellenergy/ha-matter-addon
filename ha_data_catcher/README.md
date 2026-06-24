# HA Data Catcher

![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-03A9F4?style=flat-square&logo=home-assistant)
![Platform](https://img.shields.io/badge/Platform-Multi--Arch-E91E63?style=flat-square)
![Version](https://img.shields.io/badge/Version-1.0.0-4CAF50?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-FFC107?style=flat-square)

Collects your smart home's raw events in real-time, intelligently enriches them with real-world metadata, and securely syncs them to Google Sheets for long-term storage and powerful analytics. No more complex querying—just clean, readable data where you need it.

---

## Overview

The **HA Data Catcher** is a lightweight, high-performance bridge running directly on your Home Assistant OS. It solves the problem of messy, hard-to-read device logs by transforming technical identifiers into understandable context before saving them.

On startup, the add-on connects instantly to the Home Assistant WebSocket API to stream events the moment they happen. Instead of saving a generic event like `light.bulb_1 turned on`, it queries your Custom Storage to figure out that the *Living Room Fan Light* was turned on.

Once the data is enriched with proper room names, floor levels, and hardware details, the add-on bundles everything into efficient batches and sends it directly to a Google Apps Script webhook. From there, your Google Sheets automatically populate with rich, contextual telemetry data.

---

## Architecture & Features

### Real-Time Streaming
Directly attaches to the Home Assistant Core WebSocket (`ws://homeassistant:8123/api/websocket`). Captures crucial events like `state_changed`, `call_service`, `zha_event`, and `matter_event` instantly without any polling delay.

### Intelligent Metadata Enrichment
Raw `entity_id` strings mean nothing in analytics. This add-on maps logical entities to physical context:
- **Location:** Identifies specific Rooms and Floors.
- **Hardware Topology:** Maps software entities back to physical Snaps, Docks, and Docklets.
- **True Load Types:** Categorizes devices by their actual function (e.g., Fan, Light, TV) rather than generic domains.

### Smart Device Fallback
Handles edge cases automatically. If sub-devices or Matter nodes aren't explicitly mapped in your Custom Storage, the system gracefully falls back to Home Assistant's default domain classifications to ensure no event is dropped.

### Seamless Google Sheets Sync
Enriched payloads are packaged into structured batches and pushed asynchronously to a Google Apps Script endpoint. This keeps your Home Assistant instance lightweight while offloading heavy data storage to the cloud.

---

## Configuration Details

Configuration is managed entirely through the standard Home Assistant Supervisor UI.

| Option | Description |
| :--- | :--- |
| **`apps_script_url`** | Your deployed Google Apps Script Webhook URL where the data is sent. |
| **`hub_id`** | A unique identifier for this specific Home Assistant Hub. |
| **`custom_storage_url`** | Internal URL of your Custom Data Storage add-on (Default: `http://homeassistant:8100`). |
| **`ha_token`** | A Long-Lived Access Token to authenticate the secure WebSocket connection. |
| **`debug`** | Enable verbose logging for troubleshooting in the Supervisor logs. |

---

## Installation Guide

1. **Add to Add-ons Folder:** Place the `HA_Data_Catcher` folder inside your Home Assistant `addons/` directory.
2. **Refresh Supervisor:** Navigate to **Settings > Add-ons > Add-on Store**, click the three dots (top right), and hit **"Check for updates"**.
3. **Install & Configure:** Find **HA Data Catcher** in your local add-ons list, install it, and fill out the **Configuration** tab.
4. **Start the Service:** Hit Start and check the **Log** tab to verify successful connection to both the WebSocket and your Custom Storage!

---

*Note: This collector requires an active Google Apps Script deployment (maintained in the `google_apps_script/` directory) to receive its data payloads.*
