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
    python-matter-server==7.0.1

# Copy data
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
