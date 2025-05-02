ARG BUILD_FROM
FROM $BUILD_FROM

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-wheel \
    gcc \
    python3-dev \
    musl-dev \
    libffi-dev \
    openssl-dev

# Install Python packages
RUN pip3 install --no-cache-dir \
    fastapi \
    uvicorn \
    pyjwt \
    python-jose[cryptography] \
    requests \
    websockets

# Create directories
RUN mkdir -p /data/matter_controller/credentials \
    && mkdir -p /data/logs \
    && mkdir -p /data/matter_server

# Copy data for add-on
COPY rootfs /
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
