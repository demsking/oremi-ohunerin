# Copyright 2023 Sébastien Demanou. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import logging

from oremi.core.network import get_ipv4_address
from oremi_discovery_client import DiscoveryClient, Service

from .package import APP_NAME, APP_VERSION, SERVER_HEADER

__all__ = [
  'register_discovery_service',
]


async def register_discovery_service(
  *,
  service_port: int,
  discovery_uri: str,
  discovery_cert_file: str | None = None,
  supported_languages: list[str],
  logger: logging.Logger,
) -> None:
  logger.info('Starting discovery service')

  async def register_service() -> None:
    await discovery.register(service, lambda result: logger.info(f'Subscribing result: {result}'))

  hostname = get_ipv4_address()
  ssl_context = None
  service = Service(
    name = APP_NAME,
    protocol = 'wss' if discovery_cert_file else 'ws',
    host = hostname,
    port = service_port,
    data = {
      'version': APP_VERSION,
      'languages': supported_languages,
    },
  )

  if discovery_cert_file:
    import ssl

    logger.info(f'Using certificat file "{discovery_cert_file}" for Discovery')
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.load_verify_locations(discovery_cert_file)

  discovery = DiscoveryClient(
    uri = discovery_uri,
    user_agent = SERVER_HEADER,
    logger = logger,
    on_connected = register_service,
    ssl = ssl_context,
  )

  await discovery.connect()
