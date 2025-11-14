ARG BUILD_FROM
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    python3-dev \
    py3-pip \
    gcc \
    musl-dev \
    sqlite \
    sqlite-dev \
    curl \
    jq

# Install Python dependencies
RUN pip3 install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    websockets==12.0 \
    aiofiles==23.2.1 \
    python-multipart==0.0.6 \
    pydantic==2.5.0 \
    sqlalchemy==2.0.23 \
    aiosqlite==0.19.0 \
    python-dateutil==2.8.2 \
    requests==2.31.0

# Create app directory
WORKDIR /app

# Copy application files
COPY app/ /app/
COPY run.sh /run.sh

# Make run script executable
RUN chmod +x /run.sh

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Labels
LABEL \
    io.hass.name="Schnell Storage" \
    io.hass.description="Custom data storage for Schnell Home Automation" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    maintainer="Schnell Home Automation Team"

# Start the application
CMD ["/run.sh"]
