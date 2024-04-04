FROM python:3.10-slim

RUN addgroup --system --gid 1000 oremi \
  && adduser --system --no-create-home --uid 1000 oremi

COPY models/wakeword-en /oremi/
COPY models/wakeword-fr /oremi/

RUN apt-get update \
  && apt-get install --no-install-recommends -y curl libusb-1.0-0-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY scripts/ /oremi/scripts
COPY build/requirements.txt /oremi/

RUN mkdir -p /var/oremi/models \
  && chown -R oremi:oremi /var/oremi/models \
  && pip install --no-cache-dir -r /oremi/requirements.txt \
  && rm -f /oremi/requirements.txt

COPY pyproject.toml config.json LICENSE /oremi/
COPY oremi_sds/ /oremi/oremi_sds

USER oremi
ENTRYPOINT ["/oremi/scripts/entrypoint.sh"]
