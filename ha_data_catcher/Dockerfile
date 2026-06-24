ARG BUILD_FROM
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install dependencies
RUN apk add --no-cache bash curl jq

# Copy requirements and install
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application files
COPY run.sh /run.sh
COPY app/ /app/

# Set executable permission on entrypoint
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
