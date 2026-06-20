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

RUN addgroup --system --gid 1000 olumulo \
  && adduser --system --no-create-home --uid 1000 olumulo

# Install runtime dependencies
RUN apt-get update \
  && apt-get install -y --no-install-recommends tzdata libusb-1.0-0-dev \
  && ln -fs /usr/share/zoneinfo/UTC /etc/localtime \
  && echo "UTC" > /etc/timezone \
  && dpkg-reconfigure -f noninteractive tzdata \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Copy built Python dependencies from the install-dependencies-stage stage
COPY --from=install-dependencies-stage /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=install-dependencies-stage /usr/local/bin/ /usr/local/bin/

# Binaries
COPY bin/* /opt/oremi/bin/
RUN chmod +x /opt/oremi/bin/*

# Copy application files
COPY pyproject.toml LICENSE /opt/oremi/
COPY ohunerin/ /opt/oremi/ohunerin

USER olumulo

ENV PATH="/opt/oremi/bin:$PATH"
ENV PYTHONPATH="/opt/oremi"

ENV LOG_LEVEL="INFO"
ENV LOG_FILE=

EXPOSE 5023

WORKDIR /var/oremi
ENTRYPOINT ["/opt/oremi/bin/entrypoint.sh"]
