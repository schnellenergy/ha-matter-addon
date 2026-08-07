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

**A wrong passphrase is reported within a few seconds, not at the end of the
connection budget.** NetworkManager answers `Activating connection failed` for
rejected credentials; that is treated as a credential rejection and returned
straight away as `auth_failed`, so the app can point at the password field
instead of showing a generic network error. Only genuinely transient conditions
(a stale D-Bus path, an interface not yet ready) are retried.

The hub stays discoverable through a failed attempt. The LED returns to the
normal blinking red and the app can submit new credentials over the same BLE
link — no power cycle, no re-scan.

**Credentials are written to disk only after the connection is proven**, and
success requires the interface to be connected *to the SSID that was submitted*.
A rejected password therefore leaves nothing behind: no config file for the next
boot to retry forever, and no chance of a stale connection to a different network
being read as success and shown as solid blue.

### Factory reset

1. Press and hold the physical button for **5 seconds**.
2. The LED blinks red to confirm the reset has started.
3. The hub's published IP is deleted from the cloud and the deletion is verified.
4. The saved Wi-Fi credentials are forgotten and the local configuration is
   removed. The wlan0 interface is deliberately left **enabled** — disabling it
   meant NetworkManager kept its own saved profile (so a reset hub rejoined the
   old network on the next boot) and could not activate a new one (so the next
   provisioning attempt failed, even though scanning still worked because
   `iwlist` bypasses NetworkManager).
5. BLE advertising restarts — the hub is ready for fresh setup.
6. Ethernet connectivity is preserved throughout.

**The reset requires internet access and will refuse without it.** Step 3 must
succeed before anything else is touched, because step 4 removes the only route
to the cloud — there is no second chance afterwards. A reset that cleared the hub
but left its IP record behind would leave the hub blank and waiting while the app
still believed it was configured and reachable, which is the worst of both
states.

If the hub cannot reach the cloud, the reset is refused: the hub is left exactly
as it was, and the LED alternates **red/blue** for 20 seconds to say so rather
than implying success. Ethernet counts as internet, so the recovery for a hub
whose Wi-Fi network no longer exists is:

1. Connect an Ethernet cable.
2. Hold the button for 5 seconds again.

The button stays live during those 20 seconds — a fresh 5-second hold cancels the
refusal and starts a new reset immediately, rather than being ignored until the
indication times out.

### Boot with a saved network

On a hub that has been provisioned, `run.sh` starts the add-on in reconnect mode.
The LED goes **solid red** and stays that way until the hub actually joins —
however long that takes. It never gives up: attempts repeat every 10 s
(association budget 15 s, DHCP 20 s) until the network comes back.

**Reconnection runs in the background, so BLE comes up immediately** —
advertising is live roughly 1.5 s after start. This matters: reconnection used to
run inline before the BLE service started, which left the hub undiscoverable for
up to ~6.7 minutes on boot — exactly the situation where a user needs to onboard
it, because the saved network is the thing that is gone.

Once connected the LED goes solid blue and the hub's IP is republished, so the
app finds it at its new address without any user action.

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

**Ethernet is an overlay, not a state.** Whenever a cable is connected the LED is
solid green, whatever else is happening — provisioning, a factory reset, a boot
reconnect. None of that logic is affected; only what the LED shows. Unplug the
cable and the LED immediately reveals the state the hub was in all along.

Underneath the overlay, exactly one state is shown at a time. States are ranked
and `led_controller.py` is the sole arbiter, so a lower-ranked writer can never
overwrite a higher-ranked active state.

| Colour | Pattern | Meaning | Rank |
|--------|---------|---------|------|
| Green | Solid | **Ethernet connected** — overrides everything below | overlay |
| Red | Blink (500 ms) | Factory reset in progress | highest |
| Red + Blue | Alternating (250 ms) | **Reset refused** — no internet, so the cloud IP could not be cleared. Held 20 s, then the real state returns | highest |
| Red | **Fast** blink (150 ms) | Provisioning — credentials received, connecting | high |
| Red | Solid | Reconnecting to the saved Wi-Fi. Persists **until it connects**, however long that takes | medium |
| Blue | Solid | Provisioned and connected over Wi-Fi | steady |
| Red | Blink (500 ms) | Ready to onboard / BLE advertising | lowest |
| Off | — | Shutdown | — |

**Fast blink means exactly one thing:** a Wi-Fi provisioning attempt is in
flight. Every attempt shows it, however many times credentials are sent; success
goes solid blue, failure goes back to the normal blink.

Blue additionally requires the hub to be **provisioned**. NetworkManager keeps
its own wlan0 profile which can outlive a factory reset, so "wlan0 connected" is
not on its own evidence that the hub is set up — after a reset the LED blinks
red, which is the truthful and actionable state.

### How states reach the controller

Three channels, because they have different loss requirements:

| Channel | Carries | Semantics |
|---------|---------|-----------|
| `/tmp/led_status` | routine reports from the 0.5 s network monitor | single slot, last-write-wins — a missed one costs nothing, the next is 500 ms away |
| `/tmp/led_events` | factory reset, reset refused, provisioning, reconnect, and the releases that end them | **append-only queue, lossless and ordered** |
| `/tmp/led_ethernet` | Ethernet presence | decides what is *displayed*, never what the hub *is* |

Events cannot share the single slot. The monitor rewrites it twice a second, so
an event written there can be silently replaced before the controller's 50 ms
poll reads it. A lost report is harmless; a lost *event* is not — a factory-reset
indication would never appear, and a lost release would strand the LED on a state
that outranks everything the monitor can request, permanently.

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
| `connection_timeout` | `60` | Total Wi-Fi connection budget in seconds (10–300). Split into an association phase (up to 20 s — failing here means a wrong passphrase) and a DHCP phase (the remainder — failing here means a router/DHCP problem). Each phase has a 10 s floor, so values under 20 s behave as 20 s. |
| `use_static_ip`, `static_ip`, `static_gateway`, `static_dns` | `false` / empty | Reserved for a future release; provisioning currently uses DHCP |

## Architecture

### Core services

| Component | Responsibility |
|-----------|----------------|
| `improved_ble_service.py` | BLE GATT server and provisioning orchestration (main service) |
| `button_monitor.py` | Factory-reset button monitoring with multi-backend GPIO support |
| `led_controller.py` | RGB LED status controller, and the arbiter for LED state |
| `led_states.py` | Canonical LED state list and ranking, shared by every writer |
| `supervisor_api.py` | Home Assistant Supervisor network API client |
| `firestore_helper.py` | Publishes and clears the hub IP for app-side discovery (verified) |

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
    │                     └── credentials rejected? → auth_failed returned
    │                         at once, nothing written, hub stays discoverable
    ▼
Connectivity check        associated to the EXPECTED ssid, IPv4 assigned
    ▼
Credentials persisted     atomic write + fsync + read-back verify
    │                     (only now — never before success)
    ▼
Hub IP published          app locates the hub on the LAN
    ▼
BLE advertising stops
```

### Factory reset flow

```
Button held 5 s
    ▼
Button monitor            reset confirmed, LED blinks red
    ▼
Hub IP record cleared     retried and VERIFIED against the server
    │                     └── cannot be cleared? → reset REFUSED,
    │                         hub untouched, LED alternates red/blue
    ▼
Supervisor API            Wi-Fi credentials FORGOTTEN, interface left
    │                     enabled (no cloud route after this)
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

**Hub is discoverable but the app says the setup service is missing**

The advertisement is written by the kernel, while the GATT service lives in the
add-on process. If the add-on is not running, the hub can still advertise as
`SMASH-XXXX` and accept a connection while serving only BlueZ's own services
(`1800`, `1801`, `180a`, and the LE Audio set `1843`–`184f`) — none of ours. The
app reports this specifically rather than retrying forever.

```bash
ha addons info local_smash_wifi_onboarding      # is it actually running?
ha addons logs local_smash_wifi_onboarding | grep "GATT service registered"
```

Restarting the add-on re-registers the GATT application; `run.sh` brings `hci0`
down and up on start, which also clears a stale kernel advertisement.

Enable the `debug` option for verbose logging across all components.

---

Built for SMASH · Powered by Home Assistant
