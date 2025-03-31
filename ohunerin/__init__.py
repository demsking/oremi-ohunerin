# Copyright 2023-2025 Sébastien Demanou. All Rights Reserved.
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

from .args import parse_arguments
from .logger import logger
from .package import APP_NAME
from .package import APP_VERSION
from .server import ClientInitMessage
from .server import DetectedSound
from .server import DetectorConsumer
from .server import DetectorEngine
from .server import Server
from .server import WakewordEngine
from .server import WakewordSetting

__all__ = [
  'ClientInitMessage',
  'DetectedSound',
  'DetectorConsumer',
  'DetectorEngine',
  'Server',
  'WakewordEngine',
  'WakewordSetting',
  'main',
  'start',
]


async def start() -> None:
  args = parse_arguments()

  logger.info(f"Starting {APP_NAME} {APP_VERSION}")
  logger.info(f"Log level: {'DEBUG' if logger.level == logging.DEBUG else 'INFO'}")
  logger.info(f"Model: {args.model}")
  logger.info(f"Threshold: {args.threshold}")
  logger.info(f"Config: {args.config}")

  server = Server(
    logger=logger,
    model_path=args.model,
    config_file=args.config,
    threshold=args.threshold,
    cert_file=args.cert_file,
    key_file=args.key_file,
    password=args.password,
  )

  await server.listen(args.host, args.port)
  logger.info('E ku ore mi')  # https://translate.google.com/?sl=yo&tl=en&text=E%20ku%20ore%20mi&op=translate


def main():
  try:
    asyncio.run(start())
  except KeyboardInterrupt:
    pass
