FROM python:3.11-slim

RUN addgroup --system --gid 1000 olumulo \
  && adduser --system --no-create-home --uid 1000 olumulo \
  && mkdir -p /var/oremi/models \
  && chown -R olumulo:olumulo /var/oremi/models

COPY models/ /oremi/models

RUN apt-get update \
  && apt-get install --no-install-recommends -y curl libusb-1.0-0-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY build/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /tmp/requirements.txt \
  && rm /tmp/requirements.txt

# Binaries
COPY bin/* /opt/oremi/bin/
COPY scripts/* /opt/oremi/scripts/
RUN chmod +x /opt/oremi/bin/* /opt/oremi/scripts/*

# Copy application files
COPY pyproject.toml config.json LICENSE /opt/oremi/
COPY ohunerin/ /opt/oremi/ohunerin

ARG PACKAGE_NAME
ARG PACKAGE_VERSION

USER olumulo

ENV PATH="/opt/oremi/bin:/opt/oremi/scripts:$PATH"

ENV TZ="Africa/Douala"
ENV THRESHOLD="0.1"

ENV LOG_LEVEL="info"
ENV LOG_FILE=

EXPOSE 5023
VOLUME /var/oremi/models

WORKDIR /opt/oremi
ENTRYPOINT ["/opt/oremi/bin/entrypoint.sh"]
