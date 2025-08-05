FROM python:3.11-slim

# Install system dependencies (matching your old working Dockerfile)
RUN apt-get update && apt-get install -y --no-install-recommends \
    hostapd \
    dnsmasq \
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
    systemd \
    iw \
    iputils-ping \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir \
    flask \
    requests

# Install GPIO libraries exactly like your old working code  
RUN pip install --no-cache-dir \
    gpiozero \
    lgpio \
    pigpio

# Try to install RPi.GPIO but don't fail if it doesn't work (like your old code)
RUN pip install --no-cache-dir RPi.GPIO || echo "RPi.GPIO installation failed, continuing..."

# Debug: Show what we actually installed
RUN echo "=== Installed GPIO packages ===" && pip list | grep -i gpio

# Create necessary directories
RUN mkdir -p /data /tmp /var/log /var/run/wpa_supplicant

# Copy application files
COPY onboarding.py /onboarding.py
COPY button_monitor.py /button_monitor.py
COPY run.sh /run.sh

# Make scripts executable
RUN chmod +x /run.sh /onboarding.py /button_monitor.py

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose web interface port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:80/health || exit 1

# Use run.sh as entrypoint
CMD ["/run.sh"]