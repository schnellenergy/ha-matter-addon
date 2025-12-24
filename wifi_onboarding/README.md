# SMASH Hub WiFi Onboarding

**Production-ready BLE WiFi onboarding addon for Home Assistant on Raspberry Pi 5**

## Overview

This addon enables seamless WiFi configuration for your SMASH Home Hub through Bluetooth Low Energy (BLE), with physical button factory reset support and visual LED status indicators.

## ✨ Features

- 📱 **BLE WiFi Onboarding** - Configure WiFi via mobile app (no display needed)
- 🔘 **Physical Factory Reset** - 5-second button press to reset WiFi
- 💡 **RGB LED Status** - Visual feedback for connection status
- 🌐 **Dual Network Support** - Ethernet + WiFi with automatic failover
- 🔧 **Supervisor API Integration** - Native Home Assistant network management
- 🚀 **Raspberry Pi 5 Optimized** - Uses lgpio for RPi 5 GPIO support
- 📦 **Zero Internet Required** - All dependencies pre-built in container

## 🔌 Hardware Requirements

| Component | Connection | Notes |
|-----------|-----------|-------|
| **Raspberry Pi 5** | - | With Home Assistant OS |
| **Factory Reset Button** | GPIO 17 (Pin 11) | Active-low with pull-up |
| **RGB LED - Red** | GPIO 22 (Pin 15) | Common cathode |
| **RGB LED - Green** | GPIO 23 (Pin 16) | Common cathode |
| **RGB LED - Blue** | GPIO 24 (Pin 18) | Common cathode |
| **Bluetooth** | Built-in | RPi 5 onboard BLE |

## 📦 Installation

### 1. Add Addon to Home Assistant

```bash
# Copy the wifi_onboarding directory to:
/addons/local/smash_ble_wifi_onboarding/
```

### 2. Build & Start

```bash
# In Home Assistant Advanced SSH & Web Terminal:
ha addons rebuild local_smash_ble_wifi_onboarding
ha addons start local_smash_ble_wifi_onboarding
ha addons logs local_smash_ble_wifi_onboarding -f
```

## 🎯 Usage

### Initial WiFi Setup

1. **Power on** your SMASH Hub with Ethernet connected
2. **Open mobile app** and scan for BLE devices
3. **Connect to** `SMASH-XXXX` (XXXX = last 4 digits of MAC)
4. **Send WiFi credentials** via BLE
5. **Wait for connection** - LED turns blue when connected
6. **Disconnect Ethernet** (optional) - WiFi remains active

### Factory Reset

1. **Press and hold** the physical button for **5 seconds**
2. **LED blinks red** to confirm reset initiated
3. **WiFi disconnected** - IP removed from Firestore
4. **BLE advertising starts** - Ready for fresh setup
5. **Ethernet preserved** - Network access maintained

## 💡 LED Status Indicators

| LED Color | Pattern | Meaning |
|-----------|---------|---------|
| 🔴 Red | Blinking | BLE advertising / Factory reset / No network |
| 🟢 Green | Solid | Ethernet connected |
| 🔵 Blue | Solid | WiFi connected |

## 🏗️ Architecture

### Core Services

- **`improved_ble_service.py`** - Main BLE WiFi onboarding service
- **`button_monitor.py`** - Factory reset button monitoring
- **`supervisor_api.py`** - Home Assistant Supervisor API wrapper
- **`led_controller.py`** - RGB LED status controller
- **`firestore_helper.py`** - Cloud IP address storage

### Support Utilities

- **`gpio_cleanup.py`** - GPIO resource cleanup (runs at startup)
- **`device_diagnostics.py`** - Hardware diagnostics (runs at startup)
- **`run.sh`** - Main startup orchestration script

### Configuration

- **`config.json`** - Addon configuration and GPIO mappings
- **`Dockerfile`** - Production container with pre-built dependencies

## ⚙️ Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `gpio_pin` | 17 | Button GPIO pin number |
| `hold_time` | 5 | Seconds to hold for factory reset |
| `enable_button` | true | Enable button monitoring |
| `enable_led` | true | Enable LED status indicators |
| `led_red_pin` | 22 | Red LED GPIO pin |
| `led_green_pin` | 23 | Green LED GPIO pin |
| `led_blue_pin` | 24 | Blue LED GPIO pin |
| `debug` | false | Enable debug logging |
| `connection_timeout` | 60 | WiFi connection timeout (seconds) |

## 🔒 Security

- ✅ Runs with `full_access` for GPIO and network management
- ✅ Uses Home Assistant Supervisor API for network operations
- ✅ Firestore credentials stored securely in addon data
- ✅ BLE pairing required for WiFi configuration
- ✅ Physical button required for factory reset

## 🐛 Troubleshooting

### BLE Not Advertising

```bash
# Check Bluetooth status
hciconfig

# Restart addon
ha addons restart local_smash_ble_wifi_onboarding
```

### Button Not Working

```bash
# Check GPIO diagnostics in logs
ha addons logs local_smash_ble_wifi_onboarding | grep GPIO
```

### WiFi Not Connecting

```bash
# Check Supervisor API status
ha addons logs local_smash_ble_wifi_onboarding | grep Supervisor
```

### LED Not Working

```bash
# Check LED controller logs
ha addons logs local_smash_ble_wifi_onboarding | grep LED
```

## 📊 Network Flow

```
Mobile App (BLE)
    ↓
BLE Service (improved_ble_service.py)
    ↓
Supervisor API (supervisor_api.py)
    ↓
Home Assistant Network Manager
    ↓
wlan0 Interface Connected
    ↓
IP Saved to Firestore
```

## 🔄 Factory Reset Flow

```
Button Held 5s
    ↓
Button Monitor (button_monitor.py)
    ↓
Delete IP from Firestore
    ↓
Supervisor API Disconnect WiFi
    ↓
Remove Local Config Files
    ↓
Signal BLE Service Restart
    ↓
BLE Advertising Starts
```

## 📝 Version History

### v1.0.0 (Production Release)
- ✅ Complete Supervisor API integration
- ✅ Raspberry Pi 5 GPIO support (lgpio)
- ✅ Factory reset via physical button
- ✅ RGB LED status indicators
- ✅ Dual network support (Ethernet + WiFi)
- ✅ Firestore IP management
- ✅ Zero internet dependency

---

**Production Ready** | Built for SMASH Home Hub | Powered by Home Assistant
