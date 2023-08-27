FROM python:3.10-slim

RUN addgroup --system --gid 1000 oremi \
  && adduser --system --no-create-home --uid 1000 oremi

COPY models/wakeword-en /oremi/
COPY models/wakeword-fr /oremi/

RUN apt-get update \
  && apt-get install --no-install-recommends -y libusb-1.0-0-dev=2:1.0.26-1 \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml config.json LICENSE build/requirements.txt /oremi/

RUN pip install --no-cache-dir -r /oremi/requirements.txt

COPY oremi_sds /oremi/oremi_sds

USER oremi
ENV PYTHONPATH="/oremi:$PYTHONPATH"
ENTRYPOINT [\
  "python", "-m", \
    "oremi_sds", \
      "--host", "0.0.0.0", \
      "--port", "5023", \
      "--config", "/oremi/config.json", \
      "--model", "/usr/share/tflite/yamnet.tflite" \
]

# Adding metadata at the end due to their values being subject to change a each build.
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
