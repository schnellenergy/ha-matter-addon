# SMASH Hub WiFi Onboarding Addon

A Home Assistant addon that provides BLE-based WiFi onboarding with physical button factory reset support for Raspberry Pi 5.

## Features

- ✅ **BLE WiFi Onboarding**: Connect to WiFi networks via Bluetooth mobile app
- ✅ **Physical Factory Reset**: GPIO button for hardware-based WiFi reset
- ✅ **LED Status Indicators**: RGB LED feedback for system status
- ✅ **Dual Network Support**: Ethernet + WiFi with automatic IP management
- ✅ **Raspberry Pi 5 Optimized**: Uses lgpio for native RPi 5 GPIO support
- ✅ **Production Ready**: Pre-built libraries, no internet required

## Hardware Requirements

- Raspberry Pi 5 with Home Assistant OS
- Physical button connected to GPIO 17 (pin 11) 
- RGB LED connected to GPIOs 22, 23, 24 (Red, Green, Blue)
- Bluetooth module (built-in on RPi 5)

## Core Files

### Essential Python Services
- `improved_ble_service.py` - Main BLE WiFi onboarding service
- `button_monitor.py` - Factory reset button monitor  
- `led_controller.py` - RGB LED status controller
- `ble_diagnostics.py` - Bluetooth diagnostics and setup
- `device_diagnostics.py` - System and hardware diagnostics

### GPIO and Hardware Support  
- `gpio_test.py` - Comprehensive GPIO hardware testing
- `simple_gpio_test.py` - Basic GPIO functionality test
- `permission_test.py` - GPIO permissions and access testing
- `gpio_cleanup.py` - GPIO resource cleanup utilities
- `gpio_setup.sh` - GPIO initialization script

### Configuration and Runtime
- `run.sh` - Main addon startup script
- `config.json` - Addon configuration and GPIO pin assignments  
- `Dockerfile` - Production container with pre-built dependencies

## Usage

1. **Deploy**: Upload addon to Home Assistant
2. **Commands**: ha addons rebuild local_smash_ble_wifi_onboarding

ha addons start local_smash_ble_wifi_onboarding

ha addons logs local_smash_ble_wifi_onboarding -f
in advanced ssh and web terminal
3. **Connect**: Use mobile app to connect to 'SMASH-XXXX' BLE device
4. **Setup WiFi**: Send WiFi credentials via BLE
5. **Factory Reset**: Hold physical button for 5 seconds to reset

## LED Status Indicators

- 🔴 **Red Blinking**:BLE advertising & Ready for WiFi setup also while factory reset
- 🟢 **Green Solid**: Ethernet connected  
- 🔵 **Blue Solid**: WiFi connected

## Button Behavior

- **Short Press**: No action (prevents accidental resets)
- **5-Second Hold**: Factory reset WiFi configuration
- **LED Feedback**: LED changes to red blinking after reset
- **Ethernet Preserved**: Only WiFi settings are cleared
- **Fresh Start**: Starts BLE adververtising and flow as a fresh boot as before

---

**Ready for production deployment on Raspberry Pi 5 with Home Assistant.**
