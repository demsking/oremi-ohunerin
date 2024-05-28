FROM python:3.11-slim

RUN addgroup --system --gid 1000 olumulo \
  && adduser --system --no-create-home --uid 1000 olumulo

COPY models/ /oremi/models

RUN apt-get update \
  && apt-get install --no-install-recommends -y curl libusb-1.0-0-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY build/requirements.txt /oremi/

RUN mkdir -p /var/oremi/models \
  && chown -R olumulo:olumulo /var/oremi/models \
  && pip install --no-cache-dir -r /oremi/requirements.txt \
  && rm -f /oremi/requirements.txt \
  && pip install \
    --no-cache-dir \
    -i https://test.pypi.org/simple/ \
    oremi-discovery==1.0.0b25

# Binaries
COPY bin/* /opt/oremi/bin/
RUN chmod +x /opt/oremi/bin/*

# Copy application files
COPY pyproject.toml config.json LICENSE /opt/oremi/
COPY ohunerin/ /oremi/ohunerin

ARG PACKAGE_NAME
ARG PACKAGE_VERSION

USER olumulo

ENV TZ="Africa/Douala"
ENV THRESHOLD="0.1"

ENV LOG_LEVEL="info"
ENV LOG_FILE=

# Discovery client ID
ENV CLIENT_ID="$PACKAGE_NAME/$PACKAGE_VERSION"

# Discovery service URI
ENV SERVICE_URI=

# Discovery service name
ENV SERVICE_NAME="$PACKAGE_NAME"

# Discovery service version
ENV SERVICE_VERSION="$PACKAGE_VERSION"

# Discovery URL
ENV DISCOVERY_URL=

EXPOSE 5023

WORKDIR /oremi
ENTRYPOINT ["/opt/oremi/bin/entrypoint.sh"]
