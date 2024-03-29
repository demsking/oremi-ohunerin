FROM python:3.10-slim

ARG CREATED_DATE
ARG PACKAGE_NAME
ARG MAINTAINER
ARG DESCRIPTION
ARG VERSION
ARG SOURCE_URL
ARG VENDOR
ARG LICENSE
ARG REVISION

# @see https://github.com/opencontainers/image-spec/blob/main/annotations.md
LABEL org.opencontainers.image.title="$PACKAGE_NAME"
LABEL org.opencontainers.image.description="$DESCRIPTION"
LABEL org.opencontainers.image.version="$VERSION"
LABEL org.opencontainers.image.revision="$REVISION"
LABEL org.opencontainers.image.authors="$MAINTAINER"
LABEL org.opencontainers.image.created="$CREATED_DATE"
LABEL org.opencontainers.image.source="$SOURCE_URL"
LABEL org.opencontainers.image.url="$SOURCE_URL"
LABEL org.opencontainers.image.documentation="$SOURCE_URL#readme"
LABEL org.opencontainers.image.vendor="$VENDOR"
LABEL org.opencontainers.image.licenses="$LICENSE"

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
