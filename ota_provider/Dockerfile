FROM ubuntu:22.04

# Install required dependencies
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

# Copy the OTA provider binary
COPY chip-ota-provider-app /usr/local/bin/chip-ota-provider-app
RUN chmod +x /usr/local/bin/chip-ota-provider-app

# Copy the run script
COPY run.sh /run.sh
RUN chmod +x /run.sh

# Set the default command
CMD ["/run.sh"]

