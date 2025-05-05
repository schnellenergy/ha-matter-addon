ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-websockets \
    py3-requests \
    py3-aiohttp \
    py3-pydantic \
    py3-cryptography \
    py3-yaml \
    jq \
    curl

# Install Python packages
RUN pip3 install --no-cache-dir \
    fastapi \
    uvicorn \
    PyJWT

# Copy files
COPY rootfs/matter_controller /matter_controller
COPY rootfs/usr/bin/debug-install.sh /usr/bin/debug-install.sh
COPY run.sh /

# Create data directories
RUN mkdir -p /data/matter_controller/credentials \
    && mkdir -p /data/logs \
    && mkdir -p /data/matter_server

# Make scripts executable
RUN chmod +x /usr/bin/debug-install.sh \
    && chmod +x /run.sh

CMD [ "/run.sh" ]
