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
import websockets.legacy.server
from oremi_core.wsserver import WebsocketConnection
from oremi_core.wsserver import WebsocketServer

from .detector import DetectorConsumer
from .detector import DetectorEngine
from .models import create_detected_sound_object
from .models import DetectedSound
from .models import InitMessage
from .models import ServerInitMessage
from .models import SoundType
from .models import WakewordSetting
from .package import APP_NAME
from .package import APP_VERSION
from .wakeword import WakewordEngine

__all__ = [
  'DetectedSound',
  'DetectorConsumer',
  'DetectorEngine',
  'InitMessage',
  'Server',
  'WakewordEngine',
  'WakewordSetting',
]


HTTP_HEADER = f"{APP_NAME}/{APP_VERSION}"


class Server(WebsocketServer):
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
      server_header=HTTP_HEADER,
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
          self.config[language] = WakewordSetting.from_dict(locale_config)
      else:
        raise ValueError('Invalid config file format: expected a dictionary')

  def _handle_connection_close(
    self,
    websocket: websockets.legacy.server.WebSocketServerProtocol,
    exception: websockets.exceptions.ConnectionClosedOK,
  ):
    if exception.reason:
      self.logger.info(f"Connection closed {websocket.remote_address} with code {exception.code}. Reason: {exception.reason}")
    else:
      self.logger.info(f"Connection closed {websocket.remote_address} with code {exception.code}")

  async def _handle_detection_result(
    self,
    websocket: websockets.legacy.server.WebSocketServerProtocol,
    sound_type: SoundType,
    sound_name: str | None,
    score: float,
  ) -> None:
    if sound_name:
      sound = create_detected_sound_object(sound_type, sound_name, score)
      message = json.dumps(sound)
      await websocket.send(message)

  async def _process_request(
    self,
    websocket: WebsocketConnection,
    message: bytes,
  ):
    return super()._process_request(websocket, message)

  def _parse_request(
    self,
    setting: WakewordSetting,
    request: InitMessage,
  ) -> tuple[WakewordEngine | None, DetectorConsumer | None]:
    wakeword_engine: WakewordEngine | None = None
    consumer: DetectorConsumer | None = None

    for feature in request.features:
      if feature.name == 'wakeword-detection':
        wakeword_setting = setting.copy()

        if feature.wakewords:
          self.logger.info(
            f"Initializing wakeword detection feature with additional {feature.wakewords} and discriminants {feature.discriminants}"
          )

          wakeword_setting.wakewords += feature.wakewords
          wakeword_setting.discriminants += feature.discriminants
        else:
          self.logger.info('Initializing wakeword detection feature')

        wakeword_engine = WakewordEngine(wakeword_setting, self.logger)

      if feature.name == 'sound-detection':
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

        consumer = DetectorConsumer(detector, logger=self.logger)

    return wakeword_engine, consumer

  async def _handle_audio_data(
    self,
    websocket: websockets.legacy.server.WebSocketServerProtocol,
    setting: WakewordSetting,
    request: InitMessage,
  ) -> None:
    started = False
    wakeword_engine, consumer = self._parse_request(setting, request)

    try:
      event = ServerInitMessage(
        type='init',
        server=HTTP_HEADER,
        status='ready',
        languages=self.supported_languages,
      )

      await websocket.send(event.to_json())  # type: ignore
      self.logger.info(f"Connection from {websocket.remote_address} {websocket.request_headers['User-Agent']}")

      if wakeword_engine:
        wakeword_engine.start_utt()

      started = True

      async for chunk in websocket:
        if wakeword_engine:
          sound, score = await self._loop.run_in_executor(self.pool, wakeword_engine.process_raw, chunk)  # type: ignore
          await self._handle_detection_result(websocket, 'wakeword', sound, score)

          if sound:
            if consumer:
              consumer.reset_buffer()
            continue

        if consumer:
          sound, score = consumer.process_raw(chunk)  # type: ignore
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
      if consumer:
        del consumer

      if started and wakeword_engine:
        wakeword_engine.end_utt()
        del wakeword_engine

  async def _handle_messages(
    self,
    websocket: websockets.legacy.server.WebSocketServerProtocol,
  ):
    init_timeout_timer_handler = self._loop.call_later(
      5,
      lambda: self._loop.create_task(
        websocket.close(code=1002, reason='Init Timeout'),
        name='Init Timeout Task',
      ),
    )

    try:
      message = await websocket.recv()
      init_timeout_timer_handler.cancel()
      request = InitMessage.create(message)  # type: ignore
      wakeword_setting = self.config[request.language]

      await self._handle_audio_data(websocket, wakeword_setting, request)
    except (ValueError, TypeError):
      error_message = f"Invalid Init Message: {message}"
      self.logger.error(error_message)
      await websocket.close(code=1003, reason=error_message)
