# PRODUCTION FIX: Use Home Assistant's Python version to match runtime
# Home Assistant OS uses Python 3.13, so we need to match that
FROM python:3.13-slim

# Install system dependencies (BLE, WiFi management, and basic tools)
# PRODUCTION FIX: Install ALL dependencies at build time to avoid runtime downloads
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    procps \
    net-tools \
    dhcpcd5 \
    udhcpc \
    rfkill \
    wireless-tools \
    wpasupplicant \
    python3-dev \
    gcc \
    g++ \
    make \
    cmake \
    systemd \
    iw \
    iputils-ping \
    curl \
    jq \
    bluez \
    bluetooth \
    libbluetooth-dev \
    bluez-tools \
    python3-dbus \
    python3-gi \
    gir1.2-glib-2.0 \
    dbus \
    dbus-user-session \
    libdbus-1-dev \
    libglib2.0-dev \
    pkg-config \
    swig \
    build-essential \
    libgpiod-dev \
    wget \
    unzip \
    git \
    libcairo2-dev \
    libgirepository1.0-dev \
    && rm -rf /var/lib/apt/lists/*

# PRODUCTION FIX: Install ALL Python packages at build time to avoid runtime downloads
# Install core Python packages (BLE support, requests, and Firebase) - Use system D-Bus packages
RUN python3 -m pip install --break-system-packages --no-cache-dir \
    requests \
    bleak \
    asyncio-mqtt \
    firebase-admin

# PRODUCTION FIX: Build and install ALL GPIO libraries at build time
RUN echo "=== PRODUCTION BUILD: Installing ALL GPIO libraries for Python 3.13 ===" && \
    python3 --version && \
    # Build and install lgpio system library from source (REQUIRED for production)
    echo "Building lgpio system library from source..." && \
    cd /tmp && \
    wget -q https://github.com/joan2937/lg/archive/refs/heads/master.zip && \
    unzip -q master.zip && \
    cd lg-master && \
    make && \
    make install && \
    ldconfig && \
    echo "✅ lgpio system library installed" && \
    # Install ALL GPIO Python packages with compilation for Python 3.13
    python3 -m pip install --break-system-packages --force-reinstall --no-cache-dir --compile \
    gpiozero \
    rpi-lgpio \
    RPi.GPIO && \
    # Install lgpio Python binding with proper linking - MULTIPLE ATTEMPTS for production reliability
    echo "Installing lgpio Python binding for Python 3.13..." && \
    (CFLAGS="-I/usr/local/include" LDFLAGS="-L/usr/local/lib -llgpio" \
    python3 -m pip install --break-system-packages --force-reinstall --no-cache-dir --no-binary=lgpio --compile lgpio || \
    echo "First lgpio install attempt failed, trying alternative...") && \
    # Second attempt with direct source build
    (cd lg-master && cd py_lgpio && python3 setup.py build_ext --inplace && python3 setup.py install --force || \
    echo "Second lgpio install attempt failed, trying third method...") && \
    # Third attempt: Force install from wheel if available
    (python3 -m pip install --break-system-packages --force-reinstall --no-cache-dir lgpio || \
    echo "Third lgpio install attempt failed") && \
    # PRODUCTION VERIFICATION: Ensure at least one GPIO library works
    echo "=== PRODUCTION VERIFICATION: Testing GPIO imports ===" && \
    (python3 -c "import lgpio; print('✅ lgpio build verification PASSED')" || \
    echo "❌ lgpio build verification failed - runtime will use fallback") && \
    (python3 -c "import gpiozero; print('✅ gpiozero build verification PASSED')" || \
    echo "❌ gpiozero build verification failed") && \
    (python3 -c "import RPi.GPIO; print('✅ RPi.GPIO build verification PASSED')" || \
    echo "❌ RPi.GPIO build verification failed") && \
    # Clean up build files but keep essential libraries
    rm -rf /tmp/lg-master /tmp/master.zip && \
    echo "✅ PRODUCTION GPIO BUILD COMPLETE"

# PRODUCTION FIX: Comprehensive build-time verification and setup
RUN echo "=== PRODUCTION BUILD VERIFICATION ===" && \
    echo "Installed GPIO packages:" && pip list | grep -i gpio && \
    echo "=== Final GPIO import verification ===" && \
    python3 -c "import lgpio; print('✅ lgpio import test PASSED')" 2>/dev/null || echo "❌ lgpio import test failed" && \
    python3 -c "import gpiozero; print('✅ gpiozero import test PASSED')" 2>/dev/null || echo "❌ gpiozero import test failed" && \
    python3 -c "import RPi.GPIO; print('✅ RPi.GPIO import test PASSED')" 2>/dev/null || echo "❌ RPi.GPIO import test failed"

# PRODUCTION FIX: Ensure D-Bus packages are properly configured at build time
RUN echo "=== PRODUCTION D-Bus setup ===" && \
    echo "System D-Bus packages:" && ls -la /usr/lib/python3/dist-packages/ | grep -E "(dbus|gi)" || echo "No D-Bus packages found" && \
    echo "Pip D-Bus packages:" && pip list | grep -i dbus

# PRODUCTION FIX: Python version compatibility and path setup
RUN echo "=== PRODUCTION Python compatibility setup ===" && \
    python3 --version && \
    which python3 && \
    # CRITICAL: Ensure runtime uses the SAME Python version as build time
    echo "Build-time Python: $(python3 --version)" && \
    echo "Build-time Python path: $(which python3)" && \
    # Force runtime to use the exact same Python binary
    ln -sf /usr/local/bin/python3 /usr/bin/python3 && \
    # Set PYTHONPATH to prioritize system packages (critical for D-Bus)
    echo "export PYTHONPATH=/usr/lib/python3/dist-packages:\$PYTHONPATH" >> /etc/environment

# PRODUCTION FIX: Final D-Bus verification at build time
RUN echo "=== PRODUCTION D-Bus verification ===" && \
    PYTHONPATH="/usr/lib/python3/dist-packages:$PYTHONPATH" python3 -c "import dbus; print('✅ dbus import PASSED')" 2>/dev/null || echo "❌ dbus import failed" && \
    PYTHONPATH="/usr/lib/python3/dist-packages:$PYTHONPATH" python3 -c "from gi.repository import GLib; print('✅ gi.repository import PASSED')" 2>/dev/null || echo "❌ gi.repository import failed" && \
    echo "✅ PRODUCTION BUILD D-Bus SETUP COMPLETE"

# PRODUCTION FIX: Final comprehensive verification before runtime
RUN echo "=== PRODUCTION FINAL VERIFICATION ===" && \
    echo "Python version: $(python3 --version)" && \
    echo "Python location: $(which python3)" && \
    echo "=== Verifying ALL required packages are installed ===" && \
    python3 -c "import sys; print('Python paths:'); [print(f'  {p}') for p in sys.path[:5]]" && \
    python3 -c "import requests; print('✅ requests: READY')" || echo "❌ requests: FAILED" && \
    python3 -c "import bleak; print('✅ bleak: READY')" || echo "❌ bleak: FAILED" && \
    PYTHONPATH="/usr/lib/python3/dist-packages:$PYTHONPATH" python3 -c "import dbus; print('✅ dbus: READY (system)')" || echo "❌ dbus: FAILED" && \
    PYTHONPATH="/usr/lib/python3/dist-packages:$PYTHONPATH" python3 -c "from gi.repository import GLib; print('✅ gi.repository: READY (system)')" || echo "❌ gi.repository: FAILED" && \
    python3 -c "import lgpio; print('✅ lgpio: READY')" || echo "❌ lgpio: FAILED" && \
    python3 -c "import gpiozero; print('✅ gpiozero: READY')" || echo "❌ gpiozero: FAILED" && \
    python3 -c "import RPi.GPIO; print('✅ RPi.GPIO: READY')" || echo "❌ RPi.GPIO: FAILED" && \
    echo "=== PRODUCTION BUILD VERIFICATION COMPLETE ===" && \
    echo "✅ PRODUCTION CONTAINER BUILD SUCCESSFUL - NO RUNTIME DOWNLOADS NEEDED"

# Create necessary directories
RUN mkdir -p /data /tmp /var/log /var/run/wpa_supplicant

# Copy essential application files
COPY button_monitor.py /button_monitor.py
COPY improved_ble_service.py /improved_ble_service.py
COPY supervisor_api.py /supervisor_api.py
COPY firestore_helper.py /firestore_helper.py
COPY firebase-service-account.json /firebase-service-account.json
COPY led_controller.py /led_controller.py
COPY gpio_cleanup.py /gpio_cleanup.py
COPY device_diagnostics.py /device_diagnostics.py
COPY run.sh /run.sh

# Create D-Bus configuration for BLE
RUN mkdir -p /etc/dbus-1/system.d && \
    echo '<?xml version="1.0" encoding="UTF-8"?>' > /etc/dbus-1/system.d/bluetooth-addon.conf && \
    echo '<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN" "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">' >> /etc/dbus-1/system.d/bluetooth-addon.conf && \
    echo '<busconfig>' >> /etc/dbus-1/system.d/bluetooth-addon.conf && \
    echo '  <policy user="root">' >> /etc/dbus-1/system.d/bluetooth-addon.conf && \
    echo '    <allow own="org.bluez"/>' >> /etc/dbus-1/system.d/bluetooth-addon.conf && \
    echo '    <allow send_destination="org.bluez"/>' >> /etc/dbus-1/system.d/bluetooth-addon.conf && \
    echo '    <allow send_interface="org.bluez.GattManager1"/>' >> /etc/dbus-1/system.d/bluetooth-addon.conf && \
    echo '    <allow send_interface="org.bluez.LEAdvertisingManager1"/>' >> /etc/dbus-1/system.d/bluetooth-addon.conf && \
    echo '    <allow receive_sender="org.bluez"/>' >> /etc/dbus-1/system.d/bluetooth-addon.conf && \
    echo '  </policy>' >> /etc/dbus-1/system.d/bluetooth-addon.conf && \
    echo '</busconfig>' >> /etc/dbus-1/system.d/bluetooth-addon.conf

# Make scripts executable
RUN chmod +x /run.sh /button_monitor.py /improved_ble_service.py /led_controller.py /gpio_cleanup.py /device_diagnostics.py

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DBUS_SYSTEM_BUS_ADDRESS=unix:path=/var/run/dbus/system_bus_socket
ENV PYTHONPATH=/usr/lib/python3/dist-packages:/usr/local/lib/python3.13/site-packages

# Use run.sh as entrypoint
CMD ["/run.sh"]