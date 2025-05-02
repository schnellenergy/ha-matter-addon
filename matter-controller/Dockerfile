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
    openssl-dev \
    bash \
    git

# Install Python packages
RUN pip3 install --no-cache-dir \
    fastapi==0.95.2 \
    uvicorn==0.22.0 \
    pydantic==1.10.8 \
    python-jose==3.3.0 \
    aiohttp==3.8.4 \
    requests==2.28.2 \
    python-matter-server==5.0.0

# Create directories
RUN mkdir -p /data/matter_controller/credentials \
    && mkdir -p /data/logs \
    && mkdir -p /data/matter_server

# Copy data for add-on
COPY rootfs /
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
