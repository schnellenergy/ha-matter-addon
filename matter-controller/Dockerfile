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
    python3-full \
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

# Create a virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install the Matter Server using a more reliable approach
# First, install the dependencies for the Matter Server
RUN pip install --no-cache-dir \
    wheel \
    setuptools \
    cryptography

# Install the Home Assistant Matter packages
RUN pip install --no-cache-dir \
    home-assistant-chip-core==2024.11.0 \
    home-assistant-chip-clusters==2024.11.0

# Clone the Matter Server repository
RUN mkdir -p /opt && \
    cd /opt && \
    git clone --depth 1 -b ${MATTER_SERVER_VERSION} https://github.com/home-assistant-libs/python-matter-server.git && \
    cd python-matter-server && \
    pip install --no-cache-dir -e .

# Install Python packages for our API and Matter Server
RUN pip install --no-cache-dir \
    fastapi==0.95.2 \
    uvicorn==0.22.0 \
    pydantic==1.10.8 \
    python-jose==3.3.0 \
    aiohttp==3.8.4 \
    requests==2.28.2 \
    websockets==11.0.3 \
    colorlog \
    zeroconf \
    PyJWT \
    python-multipart

# Create directories
RUN mkdir -p /data/matter_controller/credentials \
    && mkdir -p /data/logs \
    && mkdir -p /data/matter_server \
    && mkdir -p /usr/bin

# Copy data for add-on
COPY rootfs /
COPY run.sh /

# Ensure scripts have correct permissions
RUN chmod 755 /usr/bin/debug-install.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
