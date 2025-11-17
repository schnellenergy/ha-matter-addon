FROM alpine:3.18

# Install Python and required packages
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-setuptools \
    py3-wheel \
    sqlite \
    sqlite-dev \
    curl \
    && pip3 install --no-cache-dir \
    flask \
    flask-cors \
    flask-socketio \
    python-socketio \
    eventlet \
    requests \
    pyyaml

# Copy application files
COPY app/ /app/
COPY run.sh /
RUN chmod a+x /run.sh

# Set working directory
WORKDIR /app

# Create data directory
RUN mkdir -p /data/custom_storage

# Expose port
EXPOSE 8100

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8100/health || exit 1

# Run the application
CMD ["/run.sh"]
