FROM python:3.11-slim

RUN addgroup --system --gid 1000 olumulo \
  && adduser --system --no-create-home --uid 1000 olumulo

COPY models/ /var/oremi/models
COPY models/yamnet.tflite /var/oremi/models/

RUN apt-get update \
  && apt-get install --no-install-recommends -y libusb-1.0-0-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY build/requirements.txt /opt/oremi/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /opt/oremi/requirements.txt

# Binaries
COPY bin/* /opt/oremi/bin/
RUN chmod +x /opt/oremi/bin/*

# Copy application files
COPY pyproject.toml config.json LICENSE /opt/oremi/
COPY ohunerin/ /opt/oremi/ohunerin

USER olumulo

ENV PATH="/opt/oremi/bin:$PATH"
ENV PYTHONPATH="/opt/oremi:$PYTHONUSERBASE:$PYTHONPATH"

ENV TZ="Africa/Douala"
ENV THRESHOLD="0.1"

ENV LOG_LEVEL="info"
ENV LOG_FILE=

EXPOSE 5023

WORKDIR /var/oremi
ENTRYPOINT ["/opt/oremi/bin/entrypoint.sh"]
