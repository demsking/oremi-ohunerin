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
import concurrent.futures
import json
import logging
import os
import traceback

import websockets.exceptions
import websockets.legacy.protocol
import websockets.legacy.server
from oremi_core.wsserver import WebSocketConnection
from oremi_core.wsserver import WebSocketServer

from .detector import DetectorConsumer
from .detector import DetectorEngine
from .models import ClientInitMessage
from .models import create_detected_sound_object
from .models import DetectedSound
from .models import ServerInitMessage
from .models import ServerReadyMessage
from .models import SoundType
from .models import WakewordSetting
from .package import APP_NAME
from .package import APP_VERSION
from .wakeword import WakewordEngine

__all__ = [
  'ClientInitMessage',
  'DetectedSound',
  'DetectorConsumer',
  'DetectorEngine',
  'Server',
  'WakewordEngine',
  'WakewordSetting',
]


SERVER_NAME = f"{APP_NAME}/{APP_VERSION}"
MAX_REASON_LENGTH = 123


class Server(WebSocketServer):
  def __init__(
    self,
    *,
    model_path: str,
    config_file: str,
    threshold: float,
    cert_file: str | None = None,
    key_file: str | None = None,
    password: str | None = None,
    logger: logging.Logger,
  ) -> None:
    super().__init__(
      server_header=SERVER_NAME,
      cert_file=cert_file,
      key_file=key_file,
      password=password,
      logger=logger,
    )
    self.verbose = logger.isEnabledFor(logging.DEBUG)
    self.config: dict[str, WakewordSetting] = {}
    self.num_threads = os.cpu_count() or 1
    self.threshold = threshold
    self.model_path = model_path

    self.pool = concurrent.futures.ThreadPoolExecutor(
      max_workers=self.num_threads,
      thread_name_prefix=APP_NAME,
    )

    self._loop = asyncio.get_running_loop()
    self._load_config_file(config_file)

  @property
  def supported_languages(self) -> list[str]:
    return list(self.config.keys())

  @staticmethod
  def truncate_reason(reason: str) -> str:
    if len(reason) > MAX_REASON_LENGTH:
      return reason[: MAX_REASON_LENGTH - 3] + '...'
    return reason

  def _create_ssl_context(
    self,
    *,
    cert_file: str,
    key_file: str | None = None,
    password: str | None = None,
  ):
    ssl_context = None

    if cert_file:
      import ssl

      ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
      self.logger.info(f'Using certificat file "{cert_file}"')

      if key_file:
        self.logger.info(f'Using key file "{key_file}"')

      ssl_context.load_cert_chain(cert_file, key_file, password)

    return ssl_context

  def _load_config_file(self, config_file: str):
    self.logger.info(f"Loading wakeword config from {config_file}")

    with open(config_file, encoding='utf-8') as file:
      config_content = json.load(file)

      if isinstance(config_content, dict):
        for language, locale_config in config_content.items():
          self.logger.info(f'Loading wakeword config for language "{language}": {locale_config["wakewords"]}')
          self.config[language] = WakewordSetting.model_validate(locale_config)
      else:
        raise ValueError('Invalid config file format: expected a dictionary')

  def _handle_connection_close(
    self,
    websocket: WebSocketConnection,
    exception: websockets.exceptions.ConnectionClosedOK,
  ):
    if exception.reason:
      self.logger.info(f"Connection closed {websocket.remote_address} with code {exception.code}. Reason: {exception.reason}")
    else:
      self.logger.info(f"Connection closed {websocket.remote_address} with code {exception.code}")

  async def _handle_detection_result(
    self,
    websocket: WebSocketConnection,
    sound_type: SoundType,
    sound_name: str,
    score: float,
  ) -> None:
    sound = create_detected_sound_object(sound_type, sound_name, score)
    message = json.dumps(sound)

    await websocket.send(message)

  async def _process_request(
    self,
    websocket: WebSocketConnection,
    message: bytes,
  ):
    return super()._process_request(websocket, message)

  def _parse_client_init_message(self, request: ClientInitMessage) -> tuple[WakewordEngine | None, DetectorConsumer | None]:
    wakeword_engine: WakewordEngine | None = None
    detector_consumer: DetectorConsumer | None = None

    for feature in request.features:
      if feature.name == 'wakeword-detection':
        if feature.wakewords:
          self.logger.info(
            f"Initializing wakeword detection feature with additional {feature.wakewords} and discriminants {feature.discriminants}"
          )

          wakeword_setting = self.config[feature.language].copy()
          wakeword_setting.wakewords += feature.wakewords
          wakeword_setting.discriminants += feature.discriminants
        else:
          self.logger.info('Initializing wakeword detection feature')
          wakeword_setting = self.config[feature.language]

        wakeword_engine = WakewordEngine(wakeword_setting, self.logger)
      elif feature.name == 'sound-detection':
        if feature.allowlist:
          self.logger.info(f"Initializing sound detection feature and allowlist {', '.join(feature.allowlist)}")
        else:
          self.logger.info('Initializing sound detection feature')

        detector = DetectorEngine(
          model=self.model_path,
          score_threshold=self.threshold,
          num_threads=self.num_threads,
          logger=self.logger,
          allowlist=feature.allowlist,
        )

        detector_consumer = DetectorConsumer(detector, logger=self.logger)

    return wakeword_engine, detector_consumer

  async def _handle_audio_data(self, websocket: WebSocketConnection) -> None:
    try:
      message = await websocket.recv()
      request = ClientInitMessage.model_validate_json(message)
      wakeword_engine, detector_consumer = self._parse_client_init_message(request)
    except (ValueError, AttributeError, TypeError) as error:
      error_message = f"Invalid Init Message: {message}. Error: {error}"
      await websocket.close(code=1003, reason=Server.truncate_reason(error_message))
      self.logger.error(error_message)

      if self.verbose:
        traceback.print_exc()

      return

    if wakeword_engine is None and detector_consumer is None:
      await websocket.close(
        websockets.legacy.protocol.CloseCode.INVALID_DATA,
        'No feature provided in the init message, which is required to start listening',
      )
      return

    self.logger.info(f"Connection from {websocket.remote_address} {websocket.request_headers['User-Agent']}")
    await self._send_ready_message(websocket)

    started = False

    try:
      if wakeword_engine:
        wakeword_engine.start_utt()

      started = True

      async for chunk in websocket:
        if wakeword_engine:
          sound, score = await self._loop.run_in_executor(self.pool, wakeword_engine.process_raw, chunk)  # type: ignore

          if sound:
            await self._handle_detection_result(websocket, 'wakeword', sound, score)

            if detector_consumer:
              detector_consumer.reset_buffer()

            continue

        if detector_consumer:
          sound, score = detector_consumer.process_raw(chunk)  # type: ignore

          if sound:
            await self._handle_detection_result(websocket, 'sound', sound, score)
    except websockets.exceptions.ConnectionClosedOK as exception:
      self._handle_connection_close(websocket, exception)
    except Exception as exception:
      error_message = f"Invalid Message: {exception}"
      await websocket.close(code=1003, reason=error_message)
      self.logger.error(error_message)

      if self.verbose:
        traceback.print_exc()
    finally:
      if detector_consumer:
        del detector_consumer

      if started and wakeword_engine:
        wakeword_engine.end_utt()
        del wakeword_engine

  async def _handle_messages(self, websocket: WebSocketConnection) -> None:
    try:
      await self._send_init_message(websocket)
      await self._handle_audio_data(websocket)
    except Exception as exception:
      error_message = f"Unexpected error: {exception}"
      self.logger.error(error_message)
      await websocket.close(code=1003, reason=Server.truncate_reason(error_message))

  async def _send_init_message(self, websocket: WebSocketConnection) -> None:
    message = ServerInitMessage(
      type='init',
      server=SERVER_NAME,
      available_languages=self.supported_languages,
    )

    await websocket.send(message.model_dump_json())

  async def _send_ready_message(self, websocket: WebSocketConnection) -> None:
    message = ServerReadyMessage(
      type='ready',
    )

    await websocket.send(message.model_dump_json())
