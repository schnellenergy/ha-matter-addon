FROM alpine:3.18

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

CMD [ "/run.sh" ]
