ARG BUILD_FROM
FROM ${BUILD_FROM}

# Add Home Assistant Matter Server version
ARG MATTER_SERVER_VERSION

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    git \
    build-essential \
    libffi-dev \
    libssl-dev \
    libavahi-client-dev \
    libglib2.0-dev \
    libdbus-1-dev \
    avahi-daemon \
    dbus \
    bash \
    jq \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install the Matter Server using a more reliable approach
# First, install the dependencies for the Matter Server
RUN pip3 install --no-cache-dir \
    wheel \
    setuptools \
    cryptography

# Install the Home Assistant Matter packages
RUN pip3 install --no-cache-dir \
    home-assistant-chip-core==2023.11.0 \
    home-assistant-chip-clusters==2023.11.0

# Clone the Matter Server repository
RUN mkdir -p /opt && \
    cd /opt && \
    git clone --depth 1 -b ${MATTER_SERVER_VERSION} https://github.com/home-assistant-libs/python-matter-server.git && \
    cd python-matter-server && \
    pip3 install --no-cache-dir -e .

# Install Python packages for our API
RUN pip3 install --no-cache-dir \
    fastapi==0.95.2 \
    uvicorn==0.22.0 \
    pydantic==1.10.8 \
    python-jose==3.3.0 \
    aiohttp==3.8.4 \
    requests==2.28.2 \
    websockets==11.0.3 \
    colorlog

# Create directories
RUN mkdir -p /data/matter_controller/credentials \
    && mkdir -p /data/logs \
    && mkdir -p /data/matter_server

# Create debug script
RUN mkdir -p /usr/bin
COPY rootfs/usr/bin/debug-install.sh /usr/bin/debug-install.sh
RUN chmod +x /usr/bin/debug-install.sh

# Copy data for add-on
COPY rootfs /
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
