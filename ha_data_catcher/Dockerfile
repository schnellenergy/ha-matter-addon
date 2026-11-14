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
# Firebase credentials are NOT baked into the image. They are supplied at
# runtime through the add-on option `firebase_credentials_b64` and decoded
# by run.sh. A key committed here is published to every user of the add-on.

# Set executable permission on entrypoint
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
