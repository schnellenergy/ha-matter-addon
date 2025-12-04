# Multi-stage Dockerfile to build chip-ota-provider-app
# Stage 1: Build the binary
FROM ubuntu:22.04 AS builder

# Install build dependencies
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    gcc \
    g++ \
    pkg-config \
    libssl-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    libavahi-client-dev \
    ninja-build \
    python3-venv \
    python3-dev \
    python3-pip \
    unzip \
    libgirepository1.0-dev \
    libcairo2-dev \
    libreadline-dev \
    wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone ConnectedHomeIP repository (shallow clone for faster build)
WORKDIR /workspace
RUN git clone --depth 1 --branch master https://github.com/project-chip/connectedhomeip.git

# Build the OTA provider app
WORKDIR /workspace/connectedhomeip
RUN scripts/examples/gn_build_example.sh examples/ota-provider-app/linux \
    out/ota-provider-app chip_config_network_layer_ble=false

# Stage 2: Runtime image
FROM ubuntu:22.04

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    bash \
    jq \
    libssl3 \
    libavahi-compat-libdnssd1 \
    libglib2.0-0 \
    libdbus-1-3 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create directory for OTA files
RUN mkdir -p /share/ota-files

# Copy the OTA provider binary from builder stage
COPY --from=builder /workspace/connectedhomeip/out/ota-provider-app/chip-ota-provider-app /usr/local/bin/chip-ota-provider-app
RUN chmod +x /usr/local/bin/chip-ota-provider-app

# Copy the run script
COPY run.sh /run.sh
RUN chmod +x /run.sh

# Set the default command
CMD ["/run.sh"]

