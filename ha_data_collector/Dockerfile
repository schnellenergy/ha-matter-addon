ARG BUILD_FROM
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install requirements for add-on
RUN \
  apk add --no-cache \
  python3 \
  py3-pip \
  py3-setuptools \
  py3-wheel \
  tzdata \
  bash \
  jq

# Python 3 HTTP Server
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python packages
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy data for add-on
COPY run.sh /
COPY app/ /app/

# Make run script executable
RUN chmod a+x /run.sh

# Create templates directory
RUN mkdir -p /app/templates

# Labels
LABEL \
  io.hass.name="Home Assistant Data Collector" \
  io.hass.description="Collects HA events and sends to Google Sheets" \
  io.hass.arch="armhf|aarch64|i386|amd64|armv7" \
  io.hass.type="addon" \
  io.hass.version="1.0.0"

CMD [ "/run.sh" ]
