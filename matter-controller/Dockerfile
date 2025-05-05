ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    git \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev \
    avahi-dev \
    glib-dev \
    dbus-dev \
    bash \
    jq \
    curl \
    wget

# Install Python packages
RUN pip3 install --no-cache-dir \
    wheel \
    setuptools \
    cryptography \
    fastapi \
    uvicorn \
    pydantic \
    python-jose \
    aiohttp \
    requests \
    websockets \
    colorlog \
    PyJWT \
    python-multipart

# Create a simple mock Matter Server
RUN mkdir -p /opt/matter_server
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
