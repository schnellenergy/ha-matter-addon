ARG BUILD_FROM
FROM $BUILD_FROM

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    bash

# Install Python packages
RUN pip3 install --no-cache-dir \
    fastapi==0.95.2 \
    uvicorn==0.22.0 \
    pydantic==1.10.8

# Create directories
RUN mkdir -p /data/matter_controller/credentials \
    && mkdir -p /data/logs \
    && mkdir -p /data/matter_server

# Copy data for add-on
COPY rootfs /
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
