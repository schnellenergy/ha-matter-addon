FROM ubuntu:24.04

# Install dependencies
# Install dependencies (includes python3-venv)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    libssl-dev \
    libavahi-compat-libdnssd-dev \
    curl \
    build-essential \
    unzip \
    iproute2 \
    avahi-daemon \
    libglib2.0-dev \
    sudo \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy your application code
COPY connected_home_ip/ ./connected_home_ip/
COPY run.sh /run.sh

# Make the run script executable
RUN chmod +x /run.sh

# Create and activate virtualenv, install Python packages
RUN python3 -m venv /opt/venv \
    && . /opt/venv/bin/activate \
    && pip install --no-cache-dir flask flask-cors

# Use venv by default
ENV PATH="/opt/venv/bin:$PATH"

# Expose Flask port
EXPOSE 6000

# Run the run.sh script on container start
CMD ["/run.sh"]
