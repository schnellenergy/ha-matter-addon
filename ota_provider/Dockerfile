ARG BUILD_FROM
FROM $BUILD_FROM

# Install required dependencies
RUN apk add --no-cache \
    bash \
    libstdc++ \
    libgcc \
    openssl \
    libcrypto3 \
    libssl3 \
    avahi-libs \
    glib \
    dbus-libs

# Create directory for OTA files
RUN mkdir -p /share/ota-files

# Copy the OTA provider binary
COPY chip-ota-provider-app /usr/local/bin/chip-ota-provider-app
RUN chmod +x /usr/local/bin/chip-ota-provider-app

# Copy the run script
COPY run.sh /run.sh
RUN chmod +x /run.sh

# Set the entrypoint
ENTRYPOINT ["/run.sh"]

