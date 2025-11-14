#!/bin/bash
"""
GPIO Device Setup Script - Simplified to match reference approach
"""

echo "[SETUP] GPIO Device Setup Script Starting..."

# Function to run commands with logging
run_cmd() {
    echo "[SETUP] Running: $*"
    "$@" 2>&1 | sed 's/^/[SETUP] /'
    return ${PIPESTATUS[0]}
}

# Check if we're running with appropriate privileges
echo "[SETUP] Current privileges:"
echo "[SETUP] UID: $(id -u), GID: $(id -g)"
echo "[SETUP] Groups: $(groups)"

# Check for GPIO devices that actually exist
echo "[SETUP] Checking available GPIO devices..."
for device in /dev/gpiochip* /dev/gpiomem* /dev/mem; do
    if [ -e "$device" ]; then
        echo "[SETUP] ✅ $device: $(ls -la $device | awk '{print $1, $3, $4}')"
        # Try to make sure it's accessible
        chmod 666 "$device" 2>/dev/null || echo "[SETUP] Cannot set permissions on $device"
    else
        echo "[SETUP] ❌ $device: Missing"
    fi
done

# Check the specific device that lgpio would use
if [ -e "/dev/gpiochip0" ]; then
    echo "[SETUP] ✅ lgpio primary device /dev/gpiochip0 is available"
else
    echo "[SETUP] ❌ lgpio primary device /dev/gpiochip0 is missing"
fi

# Final device status
echo "[SETUP] Final GPIO device status:"
ls -la /dev/gpio* 2>/dev/null | sed 's/^/[SETUP] /' || echo "[SETUP] No GPIO devices found"

echo "[SETUP] GPIO Device Setup Script Complete"
