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
    bash

# Install Python packages
RUN pip3 install --no-cache-dir \
    fastapi==0.95.2 \
    uvicorn==0.22.0 \
    pyjwt==2.6.0 \
    python-jose==3.3.0 \
    requests==2.30.0 \
    websockets==11.0.3 \
    pydantic==1.10.8 \
    typing-extensions==4.6.2

# Create directories
RUN mkdir -p /data/matter_controller/credentials \
    && mkdir -p /data/logs \
    && mkdir -p /data/matter_server

# Copy data for add-on
COPY rootfs /
COPY run.sh /
RUN chmod a+x /run.sh

# Make sure all scripts are executable
RUN find /matter_controller -type f -name "*.py" -exec chmod +x {} \;

CMD [ "/run.sh" ]
