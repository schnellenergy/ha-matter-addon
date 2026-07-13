#!/bin/bash
set -e

echo "=========================================="
echo "🚀 SMASH Hub BLE WiFi Onboarding Add-on"
echo "🏭 PRODUCTION MODE - NO INTERNET REQUIRED"
echo "=========================================="
echo "[INFO] Starting in OFFLINE mode - all packages pre-built"

# Function to set LED status
set_led_status() {
    if [ "$ENABLE_LED" = "true" ]; then
        echo "$1" > /tmp/led_status
    fi
}

# Read Home Assistant add-on configuration
CONFIG_PATH="/data/options.json"
if [ -f "$CONFIG_PATH" ]; then
    echo "[INFO] Reading Home Assistant add-on configuration..."
    GPIO_PIN=$(jq -r '.gpio_pin // 17' "$CONFIG_PATH")
    HOLD_TIME=$(jq -r '.hold_time // 5' "$CONFIG_PATH")
    ENABLE_BUTTON=$(jq -r '.enable_button // true' "$CONFIG_PATH")
    ENABLE_LED=$(jq -r '.enable_led // true' "$CONFIG_PATH")
    LED_RED_PIN=$(jq -r '.led_red_pin // 22' "$CONFIG_PATH")
    LED_GREEN_PIN=$(jq -r '.led_green_pin // 23' "$CONFIG_PATH")
    LED_BLUE_PIN=$(jq -r '.led_blue_pin // 24' "$CONFIG_PATH")
    DEBUG=$(jq -r '.debug // false' "$CONFIG_PATH")
else
    echo "[INFO] No add-on configuration found, using environment variables and defaults"
    GPIO_PIN=${GPIO_PIN:-17}
    HOLD_TIME=${HOLD_TIME:-5}
    ENABLE_BUTTON=${ENABLE_BUTTON:-true}
    ENABLE_LED=${ENABLE_LED:-true}
    LED_RED_PIN=${LED_RED_PIN:-22}
    LED_GREEN_PIN=${LED_GREEN_PIN:-23}
    LED_BLUE_PIN=${LED_BLUE_PIN:-24}
    DEBUG=${DEBUG:-false}
fi

# Export environment variables for Python scripts
export GPIO_PIN LED_RED_PIN LED_GREEN_PIN LED_BLUE_PIN ENABLE_LED ENABLE_BUTTON HOLD_TIME DEBUG

# Initial cleanup and setup
echo "[INFO] Cleaning up previous runs..."
pkill -f python 2>/dev/null || true
rm -f /tmp/led_status /tmp/wifi_reset /tmp/button_monitor.log /tmp/button_monitor.fifo

# PRODUCTION FIX: Clean up GPIO resources to prevent 'GPIO busy' errors
echo "[INFO] 🧹 Cleaning up GPIO resources..."
python3 /gpio_cleanup.py

# PRODUCTION FIX: Use pre-built GPIO libraries (NO runtime downloads)
echo "[INFO] 🔧 PRODUCTION MODE: Using pre-built GPIO libraries..."
echo "[INFO] Current Python version: $(python3 --version)"
echo "[INFO] Python binary location: $(which python3)"

# CRITICAL: Check for Python version mismatch
RUNTIME_PYTHON=$(python3 --version | grep -o "3\.[0-9]*")
echo "[INFO] Runtime Python version: $RUNTIME_PYTHON"
if [ "$RUNTIME_PYTHON" != "3.13" ]; then
    echo "[ERROR] ❌ PYTHON VERSION MISMATCH DETECTED!"
    echo "[ERROR] ❌ Container built for Python 3.13, but runtime is using Python $RUNTIME_PYTHON"
    echo "[ERROR] ❌ This will cause GPIO library import failures"
    echo "[WARNING] ⚠️ Continuing with fallback libraries..."
fi

# PRODUCTION: Verify GPIO libraries are available from build-time installation
echo "[INFO] Verifying pre-built GPIO libraries..."
if [ -f "/usr/local/lib/liblgpio.so" ] || [ -f "/usr/lib/liblgpio.so" ]; then
    echo "[INFO] ✅ lgpio system library found (built at container build time)"
else
    echo "[WARNING] ⚠️ lgpio system library not found - will use fallback GPIO libraries"
fi

# PRODUCTION FIX: Test pre-built GPIO imports (NO downloads)
echo "[INFO] PRODUCTION: Testing pre-built GPIO libraries..."
echo "[INFO] Checking GPIO library locations..."
find /usr/local/lib/python* -name "*lgpio*" 2>/dev/null || echo "No lgpio in /usr/local/lib/python*"
find /usr/local/lib/python3.13/site-packages/ -name "*gpio*" 2>/dev/null || echo "No GPIO packages in Python 3.13 site-packages"

echo "[INFO] Testing GPIO imports (using pre-built libraries only)..."
python3 -c "
try:
    import lgpio
    print('✅ lgpio import successful (pre-built)')
    try:
        print('✅ lgpio version:', lgpio.lgpio_version())
    except AttributeError:
        print('✅ lgpio loaded (version method not available)')
    import sys
    print('✅ lgpio loaded from:', lgpio.__file__)
except ImportError as e:
    print('❌ lgpio ImportError:', str(e))
    print('❌ Will use fallback GPIO libraries')
except Exception as e:
    print('❌ lgpio Error:', type(e).__name__, str(e))
    print('❌ Will use fallback GPIO libraries')
" || echo "❌ lgpio import failed - using fallback"

python3 -c "import gpiozero; print('✅ gpiozero import successful (pre-built)')" 2>/dev/null || echo "❌ gpiozero import failed"
python3 -c "import RPi.GPIO; print('✅ RPi.GPIO import successful (pre-built)')" 2>/dev/null || echo "❌ RPi.GPIO import failed"

# Now test hardware with the installed libraries
echo "[INFO] === GPIO Hardware Status Check ==="

# Start LED Controller as a background service if enabled (more robust)
if [ "$ENABLE_LED" = "true" ]; then


    # Start LED controller for production
    echo "[INFO] 🚥 Starting LED controller (production mode)..."
    set_led_status "booting"  # Start with blinking red (no network, ready for setup)
    python3 led_controller.py &
    LED_PID=$!
    sleep 2 # Give it a moment to start

    # Check if LED controller is still running
    if kill -0 $LED_PID 2>/dev/null; then
        echo "[INFO] ✅ LED controller started successfully (PID: $LED_PID)"
    else
        echo "[WARNING] ❌ LED controller stopped unexpectedly"
        echo "[WARNING] LEDs will be simulated via log messages only"
        export ENABLE_LED=false
    fi
else
    echo "[INFO] LED monitoring disabled via configuration"
fi

# Start Button Monitor if enabled
if [ "$ENABLE_BUTTON" = "true" ]; then
    echo "[INFO] 🔘 FACTORY RESET BUTTON: Starting button monitor for GPIO $GPIO_PIN..."
    echo "[INFO] 🔘 FACTORY RESET: Hold button for ${HOLD_TIME}s to trigger factory reset"
    echo "[INFO] Button monitor will auto-detect GPIO or fallback to simulation"

    # Start the button monitor and pipe output to both file and stdout
    echo "[INFO] Starting: python3 button_monitor.py --pin $GPIO_PIN --hold $HOLD_TIME --debug"
    stdbuf -oL -eL python3 button_monitor.py --pin "$GPIO_PIN" --hold "$HOLD_TIME" --debug 2>&1 | tee -a /tmp/button_monitor.log &
    BUTTON_TEE_PID=$!
    sleep 3  # Give more time to start

    # Check if tee is still running (indirect health of monitor)
    if kill -0 $BUTTON_TEE_PID 2>/dev/null; then
        echo "[INFO] ✅ FACTORY RESET BUTTON: Monitor started successfully (tee PID: $BUTTON_TEE_PID)"
        echo "[INFO] 🔘 GPIO $GPIO_PIN monitoring active - hold for ${HOLD_TIME}s to factory reset"
        echo "[INFO] 📝 Button logs: tail -f /tmp/button_monitor.log"

        # Show initial button monitor output
        sleep 1
        if [ -f "/tmp/button_monitor.log" ]; then
            echo "[INFO] === BUTTON MONITOR STARTUP LOG ==="
            tail -10 /tmp/button_monitor.log || true
            echo "[INFO] === END BUTTON MONITOR LOG ==="
        fi
    else
        echo "[ERROR] ❌ FACTORY RESET BUTTON: Monitor output stream not running"
        echo "[ERROR] Checking button monitor log..."
        if [ -f "/tmp/button_monitor.log" ]; then
            echo "[ERROR] === BUTTON MONITOR LOG ==="
            cat /tmp/button_monitor.log || true
            echo "[ERROR] === END LOG ==="
        fi
        echo "[WARNING] You can still trigger reset by running: touch /tmp/button_trigger"
        echo "[WARNING] Or send signal: pkill -USR2 -f improved_ble_service.py"
    fi
else
    echo "[INFO] Button monitoring disabled via configuration"
fi

# Run diagnostics
echo "[INFO] Running device diagnostics..."
python3 /device_diagnostics.py

# Initialize Bluetooth (more robust for production)
echo "[INFO] Initializing Bluetooth for BLE mode..."
if hciconfig 2>/dev/null | grep -q hci0; then
    hciconfig hci0 down 2>/dev/null || true
    sleep 1
    hciconfig hci0 up 2>/dev/null || true
    hciconfig hci0 piscan 2>/dev/null || true
    echo "[INFO] ✅ Bluetooth initialized"
else
    echo "[WARNING] ⚠️ No Bluetooth adapter found - BLE service may not work properly"
    # Don't exit immediately - let the service try to start anyway
    set_led_status "error"
    # Continue with startup attempt
fi

# Start D-Bus service for BLE (more robust for production)
echo "[INFO] Configuring D-Bus for BLE..."
mkdir -p /var/run/dbus

# Check if system D-Bus is already running (Home Assistant OS)
if [ -S "/var/run/dbus/system_bus_socket" ]; then
    echo "[INFO] ✅ Using existing D-Bus system bus"
elif pgrep -f "dbus-daemon --system" > /dev/null; then
    echo "[INFO] ✅ D-Bus daemon already running"
else
    echo "[INFO] Starting new D-Bus system bus..."
    dbus-daemon --system --fork --nopidfile 2>/dev/null || echo "Warning: D-Bus start failed"
    sleep 2
fi

# Verify D-Bus is accessible (don't exit if fails)
if [ -S "/var/run/dbus/system_bus_socket" ]; then
    echo "[INFO] ✅ D-Bus socket available at /var/run/dbus/system_bus_socket"
else
    echo "[WARNING] ⚠️ D-Bus system bus not accessible - BLE may not work properly"
    # Don't exit - let the service try to start anyway
    set_led_status "error"
    # Continue with startup attempt
fi

# ==========================================
# WI-FI CONFIGURATION ANALYSIS
# ==========================================

echo "[INFO] Analyzing Wi-Fi configuration state..."
WIFI_CONFIG_FILE="/data/wifi_config.json"

if [ -f "$WIFI_CONFIG_FILE" ]; then
    echo "[INFO] Found existing Wi-Fi configuration file"

    # Validate configuration
    SAVED_SSID=$(jq -r '.ssid // ""' "$WIFI_CONFIG_FILE" 2>/dev/null || echo "")
    CONFIGURED=$(jq -r '.configured // false' "$WIFI_CONFIG_FILE" 2>/dev/null || echo "false")

    if [ -n "$SAVED_SSID" ] && [ "$SAVED_SSID" != "null" ]; then
        echo "[INFO] ✅ Valid Wi-Fi configuration found"
        echo "[INFO] Network: $SAVED_SSID"
        echo "[INFO] Configured: $CONFIGURED"

        # Set LED to solid red (attempting reconnection)
        set_led_status "wifi_connecting"

        # Enable auto-reconnection mode
        export WIFI_AUTO_RECONNECT=true
        export SAVED_WIFI_CONFIG="$WIFI_CONFIG_FILE"

        echo "[INFO] 🔴 LED: SOLID RED (attempting Wi-Fi reconnection)"

    else
        echo "[INFO] ❌ Invalid Wi-Fi configuration (no SSID)"
        echo "[INFO] Removing invalid configuration..."
        rm -f "$WIFI_CONFIG_FILE"

        # Set LED to blinking red (fresh setup)
        set_led_status "ble_advertising"

        export WIFI_AUTO_RECONNECT=false
        export SAVED_WIFI_CONFIG=""

        echo "[INFO] 🔴 LED: BLINKING RED (fresh setup mode)"
    fi
else
    echo "[INFO] ❌ No Wi-Fi configuration found"
    echo "[INFO] Starting in fresh setup mode"

    # Set LED to blinking red (fresh setup)
    set_led_status "ble_advertising"

    export WIFI_AUTO_RECONNECT=false
    export SAVED_WIFI_CONFIG=""

    echo "[INFO] 🔴 LED: BLINKING RED (fresh setup mode)"
fi

# Start main BLE service (with improved error handling)
if [ "$WIFI_AUTO_RECONNECT" = "true" ]; then
    echo "=========================================="
    echo "🔄 Wi-Fi Auto-Reconnection Mode"
    echo "📶 Network: $SAVED_SSID"
    echo "🔴 LED: SOLID RED (attempting reconnection)"
    echo "🏭 Production Mode Active"
    echo "=========================================="
else
    echo "=========================================="
    echo "🚀 Fresh Setup Mode"
    echo "📱 Device discoverable as 'SMASH-XXXX'"
    echo "🔴 LED: BLINKING RED (BLE advertising)"
    echo "🏭 Production Mode Active"
    echo "=========================================="
fi

echo "[INFO] 📡 Starting BLE WiFi onboarding service..."

# PRODUCTION FIX: Use pre-built D-Bus bindings (NO runtime downloads)
echo "[INFO] 🔍 PRODUCTION: Using pre-built D-Bus Python bindings..."
echo "[INFO] Python path: $PYTHONPATH"
echo "[INFO] Checking pre-built D-Bus packages..."

# Check system packages (should be available from build-time)
ls -la /usr/lib/python3/dist-packages/ | grep -E "(dbus|gi)" || echo "No system D-Bus packages found"

# Check pip packages (should be available from build-time)
ls -la /usr/local/lib/python3.13/site-packages/ | grep -E "(dbus|gi)" || echo "No pip D-Bus packages found"

# PRODUCTION: Test imports with system packages prioritized (NO downloads)
echo "[INFO] PRODUCTION: Testing pre-built D-Bus imports..."
export PYTHONPATH="/usr/lib/python3/dist-packages:$PYTHONPATH"
python3 -c "import sys; print('Python paths:'); [print(f'  {p}') for p in sys.path[:3]]"  # Show first 3 paths only
python3 -c "import dbus; print('✅ dbus import successful (pre-built)')" 2>/dev/null || echo "❌ dbus import failed - BLE may not work"
python3 -c "from gi.repository import GLib; print('✅ gi.repository import successful (pre-built)')" 2>/dev/null || echo "❌ gi.repository import failed - BLE may not work"

# PRODUCTION: NO runtime installations - only log if missing
if ! python3 -c "import dbus" 2>/dev/null; then
    echo "[ERROR] ❌ D-Bus Python bindings not available - this should have been built at container build time"
    echo "[ERROR] ❌ BLE service may fail to start - check Dockerfile build process"
fi

export PYTHONUNBUFFERED=1
export PYTHONPATH="/usr/lib/python3/dist-packages:$PYTHONPATH"
export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/var/run/dbus/system_bus_socket
echo "[INFO] ✅ PYTHONPATH set to: $PYTHONPATH"

if [ -f /firebase-service-account.b64 ]; then
    echo "[INFO] Decoding Firebase credentials..."
    base64 -d /firebase-service-account.b64 > /firebase-service-account.json
fi

python3 -u /improved_ble_service.py

# Cleanup on exit
echo "[INFO] Add-on is shutting down..."
set_led_status "shutdown"
sleep 2
pkill -f python 2>/dev/null || true
