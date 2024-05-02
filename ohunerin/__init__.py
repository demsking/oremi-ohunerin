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
  logger = Logger.create(APP_NAME, filename=args.log_file, level=log_level)

  server = Server(
    logger=logger,
    model_path=args.model,
    config_file=args.config,
    threshold=args.threshold,
    cert_file=args.cert_file,
    key_file=args.key_file,
    password=args.password,
  )

  logger.info(f'Starting {APP_NAME} {APP_VERSION}')
  logger.info(f'Log level {"DEBUG" if logger.level == logging.DEBUG else "INFO"}')
  logger.info(f'Model: {args.model}')
  logger.info(f'Threshold: {args.threshold}')
  logger.info(f'Config: {args.config}')

  await server.listen(args.host, args.port)
  logger.info('E ku ore mi')  # https://translate.google.com/?sl=yo&tl=en&text=E%20ku%20ore%20mi&op=translate


def main():
  try:
    asyncio.run(start())
  except KeyboardInterrupt:
    pass
