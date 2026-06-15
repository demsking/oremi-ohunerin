# Copyright 2023-2026 Sébastien Demanou. All Rights Reserved.
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
import json
import logging
import os

from .args import parse_arguments
from .logger import logger
from .models import OhunerinConfig
from .package import APP_NAME
from .package import APP_VERSION
from .server import DetectedSound
from .server import DetectorConsumer
from .server import DetectorEngine
from .server import Server
from .server import WakewordEngine
from .server import WakewordSetting

__all__ = [
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

  package_dir = os.path.dirname(__file__)
  config_file = args.config or os.path.join(package_dir, 'config.json')

  logger.info(f"Starting {APP_NAME} {APP_VERSION}")
  logger.info(f"Log level: {'DEBUG' if logger.level == logging.DEBUG else 'INFO'}")
  logger.info(f"Config: {config_file}")

  config = parse_config_file(config_file)
  log_config_details(config)

  server = Server(
    logger=logger,
    config=config,
    cert_file=args.cert_file,
    key_file=args.key_file,
    password=args.password,
  )

  logger.info(f"Model: {server.model_path}")

  await server.listen(args.host, args.port)
  logger.info('E ku ore mi')  # https://translate.google.com/?sl=yo&tl=en&text=E%20ku%20ore%20mi&op=translate


def parse_config_file(config_file: str):
  with open(config_file, encoding='utf-8') as file:
    raw = json.load(file)

  return OhunerinConfig.model_validate(raw)


def log_config_details(config: OhunerinConfig) -> None:
  """Log a human-readable summary of the loaded configuration."""
  logger.info(f"Threshold: {config.threshold}")

  if config.wakewords:
    by_lang: dict[str, list[str]] = {}
    for entry in config.wakewords:
      by_lang.setdefault(entry.language, []).append(entry.word)
    for lang, words in by_lang.items():
      logger.info(f"Wakewords [{lang}]: {', '.join(words)}")
  else:
    logger.info('Wakewords: (none)')

  if config.sounds:
    logger.info(f"Sounds ({len(config.sounds)}): {', '.join(config.sounds)}")
  else:
    logger.info('Sounds: (none — all sounds accepted)')


def main():
  try:
    asyncio.run(start())
  except KeyboardInterrupt:
    pass
