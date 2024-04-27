FROM python:3.10-slim

RUN addgroup --system --gid 1000 oremi \
  && adduser --system --no-create-home --uid 1000 oremi

COPY models/ /oremi/models

RUN apt-get update \
  && apt-get install --no-install-recommends -y curl libusb-1.0-0-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY build/requirements.txt /oremi/

RUN mkdir -p /var/oremi/models \
  && chown -R oremi:oremi /var/oremi/models \
  && pip install --no-cache-dir -r /oremi/requirements.txt \
  && rm -f /oremi/requirements.txt \
  && pip install \
            --no-cache-dir \
            -i https://test.pypi.org/simple/ \
            oremi-discovery==1.0.0b25

COPY scripts/ /oremi/scripts
COPY pyproject.toml config.json LICENSE /oremi/
COPY oremi_sds/ /oremi/oremi_sds

ARG PACKAGE_NAME
ARG PACKAGE_VERSION

USER oremi
ENV THRESHOLD="0.1"

# MQTT host configuration for discovery
ENV MQTT_HOST=

# MQTT port configuration for discovery
ENV MQTT_PORT="1883"

# Discovery client ID
ENV CLIENT_ID="$PACKAGE_NAME/$PACKAGE_VERSION"

# Discovery service URI
ENV SERVICE_URI=

# Discovery service name configuration
ENV SERVICE_NAME="$PACKAGE_NAME"

# Discovery service version configuration
ENV SERVICE_VERSION="$PACKAGE_VERSION"

# Discovery channel configuration
ENV DISCOVERY_CHANNEL="discovery"

EXPOSE 5023

WORKDIR /oremi
ENTRYPOINT ["/oremi/scripts/entrypoint.sh"]
