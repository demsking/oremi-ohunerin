#
## Stage 1: Build environment
FROM python:3.11-slim AS install-dependencies-stage

# Copy the uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the shell to /bin/bash and enable pipefail
SHELL ["/bin/bash", "-eo", "pipefail", "-c"]

# Copy and install Python dependencies
WORKDIR /src
COPY uv.lock pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml


#
## Stage 2: Runtime environment
FROM python:3.11-slim

# Set the shell to /bin/bash and enable pipefail
SHELL ["/bin/bash", "-eo", "pipefail", "-c"]

RUN addgroup --system --gid 1000 oremi \
  && adduser --system --no-create-home --uid 1000 oremi \
  && mkdir -p /oremi/data

# Install runtime dependencies
RUN apt-get update \
  && apt-get install -y --no-install-recommends libusb-1.0-0-dev curl \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Copy built Python dependencies from the install-dependencies-stage stage
COPY --chown=oremi:oremi --from=install-dependencies-stage /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --chown=oremi:oremi --from=install-dependencies-stage /usr/local/bin/ /usr/local/bin/

# Binaries
COPY --chown=oremi:oremi bin/* /oremi/bin/
RUN chmod +x /oremi/bin/*

# Copy application files
COPY --chown=oremi:oremi LICENSE /oremi/
COPY --chown=oremi:oremi models/ /oremi/models/
COPY --chown=oremi:oremi htdocs/ /oremi/htdocs/
COPY --chown=oremi:oremi data/ /oremi/data/
COPY --chown=oremi:oremi DOCUMENTATION.md /oremi/
COPY --chown=oremi:oremi pyproject.toml /oremi/
COPY --chown=oremi:oremi ohunerin/ /oremi/ohunerin

ENV PATH="/oremi/bin:$PATH"
ENV PYTHONPATH="/oremi"

ENV OREMI_OHUNERIN_SERVER_HOST="0.0.0.0"
ENV OREMI_OHUNERIN_SERVER_PORT="5023"
ENV OREMI_OHUNERIN_LOG_LEVEL="INFO"
ENV OREMI_OHUNERIN_CONFIG_PATH="/oremi/data/config.json"
ENV OREMI_OHUNERIN_MODEL_PATH="/oremi/models/yamnet.tflite"

VOLUME /oremi/data

EXPOSE 5023

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:${OREMI_OHUNERIN_SERVER_PORT}/health || exit 1

ENTRYPOINT ["/oremi/bin/entrypoint.sh"]
