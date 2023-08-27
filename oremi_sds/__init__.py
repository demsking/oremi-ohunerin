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

import argparse
import asyncio
import logging

from oremi.core.logger import Logger

from .discovery import register_discovery_service
from .package import APP_DESCRIPTION, APP_NAME, APP_VERSION
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


def parse_arguments():
  parser = argparse.ArgumentParser(prog = APP_NAME, description = APP_DESCRIPTION)

  parser.add_argument(
    '-m', '--model',
    type = str,
    required = True,
    help = 'Path to the TensorFlow Lite model filename (required).'
  )

  parser.add_argument(
    '-t', '--threshold',
    type = float,
    default = 0.1,
    help = 'Detection threshold for filtering predictions (default: 0.1).'
  )

  parser.add_argument(
    '-c', '--config',
    type = str,
    default = 'config.json',
    help = 'Path to the configuration file (default: config.json).'
  )

  parser.add_argument(
    '--host',
    type = str,
    default = '127.0.0.1',
    help = 'Host address to connect to (default: 127.0.0.1).'
  )

  parser.add_argument(
    '-p', '--port',
    type = int,
    default = 5023,
    help = 'Port number to connect to (default: 5023).'
  )

  parser.add_argument(
    '--cert-file',
    type = str,
    help = 'Path to the certificate file for secure connection.',
  )

  parser.add_argument(
    '--key-file',
    type = str,
    help = 'Path to the private key file for secure connection.',
  )

  parser.add_argument(
    '--password',
    type = str,
    help = 'Password to unlock the private key (if protected by a password).',
  )

  parser.add_argument(
    '--discovery-uri',
    type = str,
    help = 'Oremi Discovery URI to connect to.'
  )

  parser.add_argument(
    '--discovery-cert-file',
    type = str,
    help = 'Path to the certificate file to use for the connection.'
  )

  parser.add_argument(
    '--log-file',
    type = str,
    default = None,
    help = 'Name of the log file.',
  )

  parser.add_argument(
    '--verbose',
    action = 'store_true',
    help = 'Enable verbose logging.'
  )

  parser.add_argument(
    '-v', '--version',
    action = 'version',
    version = f'%(prog)s {APP_VERSION}',
    help = 'Show the version of the application.'
  )

  return parser.parse_args()


async def start() -> None:
  args = parse_arguments()
  verbose: bool = args.verbose
  log_level = logging.DEBUG if verbose else logging.INFO
  logger = Logger.create(APP_NAME, filename = args.log_file, level = log_level)
  server = Server(
    logger = logger,
    model_path = args.model,
    config_file = args.config,
    threshold = args.threshold,
    cert_file = args.cert_file,
    key_file = args.key_file,
    password = args.password,
    on_listening = (lambda: register_discovery_service(
      service_port = args.port,
      discovery_uri = args.discovery_uri,
      discovery_cert_file = args.discovery_cert_file,
      supported_languages = server.supported_languages,
      logger = logger,
    )) if args.discovery_uri else None,
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
