# Schnell Home Automation Add-ons

This repository contains a collection of custom Home Assistant add-ons developed for the Schnell Home Automation ecosystem.

## 📦 Available Add-ons

### 1. HA Data Catcher (`ha_data_catcher`)
Collects Home Assistant events in real-time, enriches them with Custom Storage metadata, and streams them securely to Firestore and BigQuery for analytics.

### 2. WiFi Onboarding (`wifi_onboarding`)
SMASH Hub BLE WiFi Onboarding Add-on. Handles initial device setup and onboarding over Bluetooth Low Energy.

### 3. Custom Data Storage (`custom_data_storage`)
Provides SQLite-based storage for handling large amounts of data efficiently. Store and access custom values for the home automation app via REST API and WebSocket.

### 4. CHIP Tool API Server (`chip_tool_api`)
Provides a simple Flask-based HTTP API wrapper around the [Connected Home over IP (CHIP)](https://github.com/project-chip/connectedhomeip) command-line tool `chip-tool`. It allows you to trigger CHIP/Matter commands via HTTP requests.

---

## 🛠 CHIP Tool API Server Documentation

## 📦 Features

- HTTP API to run `chip-tool` commands
- JSON request/response format
- Easily integratable with other services or frontends
- Docker-compatible setup
- Home Assistant add-on support

---

## 🛠 Requirements

- Python 3.6+
- `chip-tool` binary compiled and available
- Flask and Flask-CORS Python packages

---

## 🚀 Getting Started

### Running Locally

#### 1. Clone the Repository

```bash
git clone https://github.com/your-username/chip-tool-addon-python-server.git
cd chip-tool-addon-python-server
```

#### 2. Install Dependencies

```bash
pip install flask flask-cors
```

#### 3. Configure the CHIP Tool Path

Edit `connected_home_ip/python_server/chip_tool_server.py` and update the `CHIP_TOOL_PATH` variable to point to your `chip-tool` binary.

#### 4. Run the Server

```bash
python connected_home_ip/python_server/chip_tool_server.py
```

The server will start on port 6000.

### Running as a Home Assistant Add-on

#### 1. Add the Repository to Home Assistant

1. In Home Assistant, navigate to **Settings** → **Add-ons** → **Add-on Store**
2. Click the menu (⋮) in the top right corner and select **Repositories**
3. Add the URL: `https://github.com/SathanaV-Software-Engineer/chip-tool-addon-python-server`
4. Click **Add**

#### 2. Install the Add-on

1. Refresh the add-on store
2. Find "CHIP Tool API" in the list of add-ons
3. Click **Install**
4. Start the add-on after installation

The server will be available at `http://homeassistant.local:6000` or `http://[your-ha-ip]:6000`.

---

## 📡 API Endpoints

### Pair a Device

```bash
curl --location 'http://homeassistant.local:6000/pair' \
--header 'Content-Type: application/json' \
--data '{"node_id": "2", "passcode": "12988108191"}'
```

### Toggle a Device

```bash
curl --location 'http://homeassistant.local:6000/toggle' \
--header 'Content-Type: application/json' \
--data '{"node_id": "2", "endpoint_id": "1"}'
```

### Bind Devices

```bash
curl --location 'http://homeassistant.local:6000/bind' \
--header 'Content-Type: application/json' \
--data '{
  "switch_node": 1,
  "switch_endpoint": 1,
  "light_node": 2,
  "light_endpoint": 1
}'
```

---

### Use any chiptool command

```bash
curl --location 'http://homeassistant.local:6000/command' \
--header 'Content-Type: application/json' \
--data '{
  "args" : [
        "onoff",
        "toggle",
        "11",
        "1"
    ]
}'
```

---

## 🔧 Troubleshooting

### Common Issues

1. **Error: No such file or directory: 'chip-tool'**
   - Ensure the `CHIP_TOOL_PATH` in the server file points to a valid chip-tool binary
   - Check if the binary has execute permissions

2. **Connection refused**
   - Verify the server is running and listening on port 6000
   - Check if any firewall is blocking the connection

3. **Home Assistant add-on fails to start**
   - Check the add-on logs for detailed error information
   - Ensure your Home Assistant instance meets the system requirements

---

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

