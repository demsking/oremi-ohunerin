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
import logging

from ohunerin.core.args import parse_arguments
from ohunerin.core.logger import configure_logging
from ohunerin.core.package import APP_NAME
from ohunerin.core.package import APP_VERSION
from ohunerin.core.settings import log_config_details
from ohunerin.core.settings import log_group
from ohunerin.core.settings import Settings
from ohunerin.engines.detector import DetectorConsumer
from ohunerin.engines.detector import DetectorEngine
from ohunerin.engines.wakeword import WakewordEngine
from ohunerin.models.sound import DetectedSound
from ohunerin.models.wakeword import WakewordSetting
from ohunerin.server import Server
from ohunerin.server.websocket import BroadcastingWebSocketServer
from ohunerin.server.websocket import WebSocketServer

logger = logging.getLogger(__name__)

__all__ = [
  "BroadcastingWebSocketServer",
  "DetectedSound",
  "DetectorConsumer",
  "DetectorEngine",
  "Server",
  "Settings",
  "WakewordEngine",
  "WakewordSetting",
  "WebSocketServer",
  "main",
  "start",
]


async def start() -> None:
  parse_arguments()
  settings = Settings()  # pyright: ignore

  configure_logging(settings.log_level, settings.log_file)

  logger.info(f"{APP_NAME} v{APP_VERSION}")
  log_group(settings, "server", "server_host", "server_port")
  log_group(settings, "model", "threshold", "model_path")
  log_group(settings, "wakewords", "wakewords_config_path")
  log_group(settings, "sounds", "sounds_config_path")
  log_group(settings, "tls", "cert_file", "key_file", "password")
  log_group(settings, "logging", "log_level", "log_file")
  log_config_details(settings.wakewords_config, settings.sounds_config)

  server = Server(
    wakewords_config=settings.wakewords_config,
    sounds_config=settings.sounds_config,
    model=settings.model_path,
    threshold=settings.threshold,
    cert_file=settings.cert_file,
    key_file=settings.key_file,
    password=settings.password,
  )

  await server.listen(settings.server_host, settings.server_port)
  logger.info("E ku ore mi")


def main() -> None:
  try:
    asyncio.run(start())
  except KeyboardInterrupt:
    pass
