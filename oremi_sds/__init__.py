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

import asyncio
import logging

from oremi_core.logger import Logger
from oremi_core.network import get_ipv4_address
from oremi_discovery import DiscoveryService
from oremi_discovery import Service

from .args import parse_arguments
from .package import APP_NAME, APP_VERSION
from .server import (DetectedSound, DetectorConsumer, DetectorEngine, InitMessage, Server,
                     WakewordEngine, WakewordSetting)

__all__ = [
  'DetectorConsumer',
  'DetectorEngine',
  'DetectedSound',
  'InitMessage',
  'WakewordEngine',
  'WakewordSetting',
  'Server',
  'start',
  'main',
]


async def start() -> None:
  args = parse_arguments()
  verbose: bool = args.verbose
  log_level = logging.DEBUG if verbose else logging.INFO
  logger = Logger.create(APP_NAME, filename = args.log_file, level = log_level)
  hostname = get_ipv4_address()
  discovery = DiscoveryService(
    client_id=f'{APP_NAME}/{APP_VERSION}',
    logger=logger,
  )

  async def register_service():
    if args.mqtt_host and args.mqtt_port:
      await discovery.start(args.mqtt_host, args.mqtt_port)
      service = Service(
        name = APP_NAME,
        host = hostname or args.host,
        port = args.port,
      )
      discovery.publish(service)

  async def unregister_service():
    if args.mqtt_host and args.mqtt_port:
      discovery.stop()

  server = Server(
    logger = logger,
    model_path = args.model,
    config_file = args.config,
    threshold = args.threshold,
    cert_file = args.cert_file,
    key_file = args.key_file,
    password = args.password,
    on_listening=register_service,
    on_shutdown=unregister_service,
  )

  logger.info(f'Starting {APP_NAME} {APP_VERSION}')
  logger.info(f'Log level {"DEBUG" if logger.level == logging.DEBUG else "INFO"}')
  logger.info(f'Model: {args.model}')
  logger.info(f'Threshold: {args.threshold}')
  logger.info(f'Config: {args.config}')

  await server.listen(args.host, args.port)


def main():
  try:
    asyncio.run(start())
  except KeyboardInterrupt:
    pass
