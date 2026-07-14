# SMASH Wi-Fi Onboarding

![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-03A9F4?style=flat-square&logo=home-assistant)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205-E91E63?style=flat-square)
![Version](https://img.shields.io/badge/Version-1.0.0-4CAF50?style=flat-square)

Bluetooth Low Energy Wi-Fi provisioning for SMASH devices. Enables headless network setup from the SMASH mobile app — no display, keyboard, or pre-existing network connection required — with physical factory-reset support and RGB LED status indication.

---

## Overview

On first boot, the hub advertises over BLE as `SMASH-XXXX` (where `XXXX` is derived from the device MAC address). The mobile app connects, retrieves the list of Wi-Fi networks visible to the hub, and transmits the selected network's credentials. The add-on applies the configuration through the Home Assistant Supervisor network API, confirms connectivity, publishes the hub's IP address to the cloud so the app can locate it on the LAN, and stops BLE advertising.

A physical button provides field factory reset: holding it for five seconds clears the Wi-Fi configuration and returns the hub to setup mode, while Ethernet connectivity is preserved.

## Features

- **BLE Wi-Fi onboarding** — full provisioning flow from the mobile app, no display needed
- **Physical factory reset** — five-second button hold clears Wi-Fi and re-enters setup mode
- **RGB LED status** — at-a-glance connection state for installers and end users
- **Dual network support** — Ethernet and Wi-Fi operate side by side with automatic failover
- **Native network management** — all Wi-Fi configuration is applied through the Home Assistant Supervisor API
- **Raspberry Pi 5 optimized** — GPIO access via `lgpio` with automatic fallback across GPIO backends
- **Fully offline-capable** — all dependencies are pre-built into the container image; no internet access required for setup

## Hardware Requirements

| Component | Connection | Notes |
|-----------|------------|-------|
| Raspberry Pi 5 | — | Running Home Assistant OS |
| Factory reset button | GPIO 17 (pin 11) | Active-low with pull-up |
| RGB LED — red | GPIO 22 (pin 15) | Common cathode |
| RGB LED — green | GPIO 23 (pin 16) | Common cathode |
| RGB LED — blue | GPIO 24 (pin 18) | Common cathode |
| Bluetooth | Built-in | Raspberry Pi 5 onboard BLE |

All GPIO assignments are configurable (see Configuration Options).

## Installation

1. Copy this folder into your Home Assistant `/addons/local/` directory:

   ```
   /addons/local/smash_wifi_onboarding/
   ```

2. Build and start from the Home Assistant terminal:

   ```bash
   ha addons rebuild local_smash_wifi_onboarding
   ha addons start local_smash_wifi_onboarding
   ha addons logs local_smash_wifi_onboarding -f
   ```

The add-on is configured with `boot: auto` and `startup: before`, so it starts ahead of Home Assistant Core on every boot.

## Usage

### Initial Wi-Fi setup

1. Power on the SMASH device.
2. Open the mobile app and scan for BLE devices.
3. Connect to `SMASH-XXXX` (`XXXX` = last four digits of the hub MAC address).
4. Select a Wi-Fi network and submit its credentials.
5. Wait for confirmation — the LED turns solid blue once Wi-Fi is connected.
6. Ethernet may be disconnected at this point; Wi-Fi remains active.

Once provisioning succeeds, BLE advertising stops and the hub is no longer discoverable.

### Factory reset

1. Press and hold the physical button for **5 seconds**.
2. The LED blinks red to confirm the reset has started.
3. Wi-Fi is disconnected and the saved configuration is removed.
4. BLE advertising restarts — the hub is ready for fresh setup.
5. Ethernet connectivity is preserved throughout.

## BLE GATT Interface

For mobile-app integrators. Primary service UUID: `12345678-1234-1234-1234-123456789abc`

| Characteristic | UUID suffix | Access | Purpose |
|----------------|-------------|--------|---------|
| Wi-Fi Networks | `…9abd` | Read | Scanned network list (page 0), compact JSON |
| Wi-Fi Credentials | `…9abe` | Write | Submit `{"ssid": "...", "password": "..."}` to initiate connection |
| Wi-Fi Status | `…9abf` | Read / Notify | Connection state; subscribe for push updates during provisioning |
| Device Info | `…9ac0` | Read | Device name, firmware version, hardware model, MAC address |
| Network Page | `…9ac1` | Read / Write | Paginated network list — write a page number, then read that page |

Network scan results are paginated (three networks per page) and responses are size-capped to fit the BLE MTU. Scan results are cached for 30 seconds.

## LED Status Indicators

| Color | Pattern | Meaning |
|-------|---------|---------|
| Red | Blinking | Booting / BLE advertising / factory reset / error |
| Red | Solid | Reconnecting to saved Wi-Fi |
| Green | Solid | Ethernet connected (also shown for dual network) |
| Green | Blinking | Ethernet connected, no internet |
| Blue | Solid | Wi-Fi connected with internet |
| Blue | Blinking | Wi-Fi connected, no internet |
| Red + Blue | Alternating | Setup in progress |
| Off | — | Shutdown |

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `gpio_pin` | `17` | Factory-reset button GPIO pin |
| `hold_time` | `5` | Seconds the button must be held to trigger a factory reset (1–30) |
| `enable_button` | `true` | Enable button monitoring |
| `enable_led` | `true` | Enable LED status indication |
| `led_red_pin` | `22` | Red LED GPIO pin |
| `led_green_pin` | `23` | Green LED GPIO pin |
| `led_blue_pin` | `24` | Blue LED GPIO pin |
| `debug` | `false` | Enable verbose logging |
| `connection_timeout` | `60` | Wi-Fi connection timeout in seconds (10–300) |
| `use_static_ip`, `static_ip`, `static_gateway`, `static_dns` | `false` / empty | Reserved for a future release; provisioning currently uses DHCP |

## Architecture

### Core services

| Component | Responsibility |
|-----------|----------------|
| `improved_ble_service.py` | BLE GATT server and provisioning orchestration (main service) |
| `button_monitor.py` | Factory-reset button monitoring with multi-backend GPIO support |
| `led_controller.py` | RGB LED status controller |
| `supervisor_api.py` | Home Assistant Supervisor network API client |
| `firestore_helper.py` | Publishes the hub IP for app-side discovery |

### Support utilities

| Component | Responsibility |
|-----------|----------------|
| `gpio_cleanup.py` | Releases stale GPIO resources at startup |
| `device_diagnostics.py` | Hardware self-check at startup |
| `run.sh` | Startup orchestration |

### Provisioning flow

```
Mobile app (BLE)
    ▼
BLE GATT service          credentials received, connection started
    ▼
Supervisor network API    Wi-Fi profile applied to wlan0
    ▼
Connectivity check        interface up, IPv4 address assigned
    ▼
Hub IP published          app locates the hub on the LAN
    ▼
BLE advertising stops
```

### Factory reset flow

```
Button held 5 s
    ▼
Button monitor            reset confirmed, LED signals reset
    ▼
Hub IP record cleared
    ▼
Supervisor API            Wi-Fi disconnected
    ▼
Local Wi-Fi config removed
    ▼
BLE service signaled      advertising restarts, hub back in setup mode
    ▼
Ethernet preserved
```

## Troubleshooting

**BLE not advertising**

```bash
hciconfig                     # verify hci0 is UP RUNNING
ha addons restart local_smash_wifi_onboarding
```

**Button not responding**

```bash
ha addons logs local_smash_wifi_onboarding | grep GPIO
```
The add-on probes multiple GPIO backends (`lgpio`, `gpiozero`) and gpiochips automatically; the log shows which backend was selected.

**Wi-Fi not connecting**

```bash
ha addons logs local_smash_wifi_onboarding | grep Supervisor
```
Confirm the SSID is in range and the passphrase is correct; the status characteristic reports the failure reason to the app.

**LED not lighting**

```bash
ha addons logs local_smash_wifi_onboarding | grep LED
```
Verify the LED wiring matches the configured pins and that the LED is common-cathode.

Enable the `debug` option for verbose logging across all components.

---

Built for SMASH · Powered by Home Assistant
