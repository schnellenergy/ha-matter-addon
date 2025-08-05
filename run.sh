#!/bin/bash
set -e

echo "[INFO] Starting WiFi Onboarding Add-on - COMPLETE VERSION"

# Boot diagnostics
echo "[INFO] === BOOT DIAGNOSTICS ==="
echo "[INFO] Current time: $(date)"
echo "[INFO] Uptime: $(uptime)"
echo "[INFO] Network interfaces:"
ip link show | grep -E "(wlan0|eth0|end0)" || echo "No network interfaces found"
echo "[INFO] Current wlan0 status:"
ip addr show wlan0 2>/dev/null || echo "wlan0 not found"
echo "[INFO] Saved WiFi config check:"
if [ -f "/data/wifi_config.json" ]; then
    echo "[INFO] ✅ Saved WiFi config exists"
    jq -r '.ssid // "unknown"' /data/wifi_config.json 2>/dev/null | head -1 | sed 's/^/[INFO] SSID: /'
    jq -r '.static_ip // "no static IP"' /data/wifi_config.json 2>/dev/null | head -1 | sed 's/^/[INFO] Static IP: /'
else
    echo "[INFO] ❌ No saved WiFi config found"
fi
echo "[INFO] === END DIAGNOSTICS ==="
echo ""

# Read Home Assistant add-on configuration
CONFIG_PATH="/data/options.json"
if [ -f "$CONFIG_PATH" ]; then
    echo "[INFO] Reading Home Assistant add-on configuration..."
    
    # Parse configuration with fallbacks
    HOTSPOT_SSID=$(jq -r '.hotspot_ssid // "WiFi-Setup"' "$CONFIG_PATH" 2>/dev/null || echo "WiFi-Setup")
    GPIO_PIN=$(jq -r '.gpio_pin // 11' "$CONFIG_PATH" 2>/dev/null || echo "11")
    HOLD_TIME=$(jq -r '.hold_time // 5' "$CONFIG_PATH" 2>/dev/null || echo "5")
    ENABLE_BUTTON=$(jq -r '.enable_button // true' "$CONFIG_PATH" 2>/dev/null || echo "true")
    DEBUG=$(jq -r '.debug // false' "$CONFIG_PATH" 2>/dev/null || echo "false")
    AUTO_REBOOT=$(jq -r '.auto_reboot // true' "$CONFIG_PATH" 2>/dev/null || echo "true")
    CONNECTION_TIMEOUT=$(jq -r '.connection_timeout // 60' "$CONFIG_PATH" 2>/dev/null || echo "60")
    DUAL_NETWORK=$(jq -r '.dual_network // true' "$CONFIG_PATH" 2>/dev/null || echo "true")
    
    echo "[INFO] Configuration loaded from Home Assistant add-on options"
else
    echo "[INFO] No add-on configuration found, using environment variables and defaults"
    
    # Configuration from environment with defaults
    HOTSPOT_SSID=${HOTSPOT_SSID:-"WiFi-Setup"}
    GPIO_PIN=${GPIO_PIN:-11}
    HOLD_TIME=${HOLD_TIME:-5}
    ENABLE_BUTTON=${ENABLE_BUTTON:-true}
    DEBUG=${DEBUG:-false}
    AUTO_REBOOT=${AUTO_REBOOT:-true}
    CONNECTION_TIMEOUT=${CONNECTION_TIMEOUT:-60}
    DUAL_NETWORK=${DUAL_NETWORK:-true}
fi

echo "[INFO] Configuration:"
echo "  SSID: $HOTSPOT_SSID"
echo "  GPIO Pin: $GPIO_PIN"
echo "  Hold Time: $HOLD_TIME seconds"
echo "  Button Enabled: $ENABLE_BUTTON"
echo "  Debug: $DEBUG"
echo "  Dual Network: $DUAL_NETWORK"

# Cleanup function
cleanup() {
    echo "[INFO] Cleanup requested..."
    pkill -f hostapd 2>/dev/null || true
    pkill -f dnsmasq 2>/dev/null || true
    pkill -f wpa_supplicant 2>/dev/null || true
    pkill -f dhcpcd 2>/dev/null || true
    pkill -f udhcpc 2>/dev/null || true
    pkill -f python 2>/dev/null || true
    exit 0
}

# Trap signals
trap cleanup SIGTERM SIGINT

# Kill any existing processes
echo "[INFO] Cleaning existing processes..."
pkill -f hostapd 2>/dev/null || true
pkill -f dnsmasq 2>/dev/null || true
pkill -f wpa_supplicant 2>/dev/null || true
pkill -f dhcpcd 2>/dev/null || true
pkill -f udhcpc 2>/dev/null || true
pkill -f python 2>/dev/null || true
sleep 3

# Check for reset flag
if [ -f "/tmp/wifi_reset" ]; then
    echo "[INFO] Reset flag detected - clearing configuration"
    rm -f /tmp/wifi_reset
    rm -f /data/wifi_config.json
    rm -f /tmp/wpa_supplicant.conf
fi

# Setup wlan0 for hotspot mode initially
echo "[INFO] Setting up wlan0 for hotspot mode..."
ip link set wlan0 down 2>/dev/null || true
sleep 1
ip addr flush dev wlan0 2>/dev/null || true
sleep 1
ip route flush dev wlan0 2>/dev/null || true
sleep 1
ip link set wlan0 up
sleep 2
ip addr add 192.168.4.1/24 dev wlan0
sleep 1
echo "[INFO] ✅ wlan0 ready: $(ip addr show wlan0 | grep 'inet ' | head -1)"

# Create enhanced hostapd config
echo "[INFO] Creating enhanced hostapd config..."
cat > /tmp/hostapd.conf << EOF
# WiFi Onboarding Hotspot Configuration
interface=wlan0
driver=nl80211
ssid=$HOTSPOT_SSID
hw_mode=g
channel=6
auth_algs=1
wpa=0

# Improve compatibility and performance
ieee80211n=1
wmm_enabled=1

# Set country code for regulatory compliance
country_code=US

# Increase beacon interval for better mobile detection
beacon_int=100

# Enable HT capabilities for better performance
ht_capab=[HT40][SHORT-GI-20][DSSS_CCK-40]

# Improve AP discovery
ignore_broadcast_ssid=0
max_num_sta=10

# Enhanced logging for troubleshooting
logger_syslog=-1
logger_syslog_level=2
logger_stdout=-1
logger_stdout_level=2
EOF

# Start hostapd and keep it running
echo "[INFO] Starting hostapd..."
hostapd /tmp/hostapd.conf &
HOSTAPD_PID=$!
sleep 5

# Check if hostapd is still running
if kill -0 $HOSTAPD_PID 2>/dev/null; then
    echo "[INFO] ✅ hostapd running (PID: $HOSTAPD_PID)"
else
    echo "[ERROR] hostapd died"
    exit 1
fi

# Start dnsmasq with comprehensive captive portal support
echo "[INFO] Starting dnsmasq with captive portal DNS..."
dnsmasq \
    --interface=wlan0 \
    --dhcp-range=192.168.4.10,192.168.4.50,12h \
    --dhcp-option=3,192.168.4.1 \
    --dhcp-option=6,192.168.4.1 \
    --server=8.8.8.8 \
    --server=8.8.4.4 \
    --address=/#/192.168.4.1 \
    --address=/connectivitycheck.gstatic.com/192.168.4.1 \
    --address=/clients3.google.com/192.168.4.1 \
    --address=/play.googleapis.com/192.168.4.1 \
    --address=/captive.apple.com/192.168.4.1 \
    --address=/www.apple.com/192.168.4.1 \
    --address=/www.msftncsi.com/192.168.4.1 \
    --address=/msftconnecttest.com/192.168.4.1 \
    --address=/detectportal.firefox.com/192.168.4.1 \
    --address=/connectivitycheck.android.com/192.168.4.1 \
    --address=/google.com/192.168.4.1 \
    --address=/www.google.com/192.168.4.1 \
    --no-resolv \
    --no-hosts \
    --log-queries \
    --log-dhcp \
    --keep-in-foreground &

DNSMASQ_PID=$!
sleep 3

if kill -0 $DNSMASQ_PID 2>/dev/null; then
    echo "[INFO] ✅ dnsmasq running (PID: $DNSMASQ_PID)"
else
    echo "[ERROR] dnsmasq died"
    exit 1
fi

# Start button monitor if enabled
BUTTON_PID=""
if [ "$ENABLE_BUTTON" = "true" ]; then
    echo "[INFO] Starting button monitor..."
    export PYTHONUNBUFFERED=1
    
    # Test GPIO first in debug mode
    if [ "$DEBUG" = "true" ]; then
        echo "[DEBUG] Testing GPIO setup first..."
        python3 /button_monitor.py --pin $GPIO_PIN --test --debug || echo "[WARNING] GPIO test failed"
        echo "[DEBUG] Starting button monitor with debug logging..."
        python3 /button_monitor.py --pin $GPIO_PIN --hold $HOLD_TIME --debug &
    else
        python3 /button_monitor.py --pin $GPIO_PIN --hold $HOLD_TIME &
    fi
    
    BUTTON_PID=$!
    sleep 3
    
    if kill -0 $BUTTON_PID 2>/dev/null; then
        echo "[INFO] ✅ Button monitor running (PID: $BUTTON_PID)"
    else
        echo "[WARNING] Button monitor failed to start - running diagnostics..."
        python3 /button_monitor.py --pin $GPIO_PIN --test
        echo "[WARNING] Continuing without button monitoring"
        BUTTON_PID=""
    fi
else
    echo "[INFO] Button monitoring disabled"
fi

# Start web server
echo "[INFO] Starting web server..."
export PYTHONUNBUFFERED=1
export HOTSPOT_SSID=$HOTSPOT_SSID
export DUAL_NETWORK=$DUAL_NETWORK

if [ "$DEBUG" = "true" ]; then
    python3 -u /onboarding.py &
else
    python3 /onboarding.py &
fi

WEB_PID=$!
sleep 3

if kill -0 $WEB_PID 2>/dev/null; then
    echo "[INFO] ✅ Web server running (PID: $WEB_PID)"
else
    echo "[ERROR] Web server died"
    exit 1
fi

echo "[INFO] === ALL SERVICES STARTED ==="
echo "[INFO] ✅ WiFi Hotspot: $HOTSPOT_SSID"
echo "[INFO] ✅ IP Address: 192.168.4.1"
echo "[INFO] ✅ Web Interface: http://192.168.4.1"
echo "[INFO] ✅ GPIO Reset: Pin $GPIO_PIN (hold ${HOLD_TIME}s)"

if [ -n "$BUTTON_PID" ]; then
    echo "[INFO] Services: hostapd($HOSTAPD_PID), dnsmasq($DNSMASQ_PID), web($WEB_PID), button($BUTTON_PID)"
    SERVICE_PIDS="$HOSTAPD_PID $DNSMASQ_PID $WEB_PID $BUTTON_PID"
else
    echo "[INFO] Services: hostapd($HOSTAPD_PID), dnsmasq($DNSMASQ_PID), web($WEB_PID)"
    SERVICE_PIDS="$HOSTAPD_PID $DNSMASQ_PID $WEB_PID"
fi

echo "[INFO] 📱 Connect to '$HOTSPOT_SSID' and browse to http://192.168.4.1"
echo "[INFO] 🔘 Hold GPIO$GPIO_PIN button for ${HOLD_TIME}s to reset WiFi"

# Keep running and monitor services
LAST_STATUS_TIME=0
while true; do
    sleep 10
    
    # Check if critical services are still running
    if ! kill -0 $WEB_PID 2>/dev/null; then
        echo "[ERROR] Web server died - exiting"
        break
    fi
    
    # Check hostapd only if we're still in hotspot mode
    if [ -n "$HOSTAPD_PID" ] && ! kill -0 $HOSTAPD_PID 2>/dev/null; then
        echo "[WARNING] hostapd died - may have switched to client mode"
        HOSTAPD_PID=""  # Clear PID so we don't check again
    fi
    
    # Check dnsmasq only if we're still in hotspot mode
    if [ -n "$DNSMASQ_PID" ] && ! kill -0 $DNSMASQ_PID 2>/dev/null; then
        echo "[WARNING] dnsmasq died - may have switched to client mode"
        DNSMASQ_PID=""  # Clear PID so we don't check again
    fi
    
    # Restart button monitor if it died and is enabled
    if [ "$ENABLE_BUTTON" = "true" ] && [ -n "$BUTTON_PID" ] && ! kill -0 $BUTTON_PID 2>/dev/null; then
        echo "[WARNING] Button monitor died - restarting..."
        if [ "$DEBUG" = "true" ]; then
            python3 /button_monitor.py --pin $GPIO_PIN --hold $HOLD_TIME --debug &
        else
            python3 /button_monitor.py --pin $GPIO_PIN --hold $HOLD_TIME &
        fi
        BUTTON_PID=$!
        sleep 2
        if kill -0 $BUTTON_PID 2>/dev/null; then
            echo "[INFO] ✅ Button monitor restarted (PID: $BUTTON_PID)"
        else
            echo "[ERROR] Failed to restart button monitor"
            BUTTON_PID=""
        fi
    fi
    
    # Show status every 5 minutes
    CURRENT_TIME=$(date +%s)
    if [ $((CURRENT_TIME - LAST_STATUS_TIME)) -ge 300 ]; then
        echo "[INFO] Status check:"
        echo "  Web server: $(kill -0 $WEB_PID 2>/dev/null && echo 'running' || echo 'dead')"
        if [ -n "$HOSTAPD_PID" ]; then
            echo "  Hostapd: $(kill -0 $HOSTAPD_PID 2>/dev/null && echo 'running' || echo 'dead')"
        fi
        if [ -n "$DNSMASQ_PID" ]; then
            echo "  Dnsmasq: $(kill -0 $DNSMASQ_PID 2>/dev/null && echo 'running' || echo 'dead')"
        fi
        if [ -n "$BUTTON_PID" ]; then
            echo "  Button monitor: $(kill -0 $BUTTON_PID 2>/dev/null && echo 'running' || echo 'dead')"
        fi
        
        # Show current wlan0 status
        CURRENT_IP=$(ip addr show wlan0 2>/dev/null | grep 'inet ' | head -1 | awk '{print $2}' || echo "no IP")
        echo "  wlan0 IP: $CURRENT_IP"
        
        LAST_STATUS_TIME=$CURRENT_TIME
    fi
done

cleanup
