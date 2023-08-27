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
import concurrent.futures
import json
import logging
import os
import traceback
from typing import Callable, Coroutine

import websockets.exceptions
import websockets.legacy.server

from .detector import DetectorConsumer, DetectorEngine
from .models import DetectedSound, InitMessage, WakewordSetting, create_detected_sound_object
from .package import APP_NAME, SERVER_HEADER
from .wakeword import WakewordEngine

__all__ = [
  'DetectorConsumer',
  'DetectorEngine',
  'DetectedSound',
  'InitMessage',
  'WakewordEngine',
  'WakewordSetting',
  'Server',
]


class Server:
  def __init__(
    self,
    *,
    model_path: str,
    config_file: str,
    threshold: float,
    cert_file: str | None = None,
    key_file: str | None = None,
    password: str | None = None,
    on_listening: Callable[[], Coroutine] | None = None,
    logger: logging.Logger,
  ) -> None:
    self.verbose = logger.level != logging.INFO
    self.config: dict[str, WakewordSetting] = {}
    self.logger = logger
    self.on_listening = on_listening
    num_threads = os.cpu_count() or 1
    self.pool = concurrent.futures.ThreadPoolExecutor(num_threads, thread_name_prefix = APP_NAME)
    self.ssl_context = self._create_ssl_context(cert_file = cert_file, key_file = key_file, password = password)
    self._loop = asyncio.get_running_loop()
    self._load_config_file(config_file)
    self.detector = DetectorEngine(
      model = model_path,
      score_threshold = threshold,
      num_threads = num_threads,
      logger = self.logger,
    )

  @property
  def supported_languages(self):
    return list(self.config.keys())

  def _create_ssl_context(self, *, cert_file: str, key_file: str | None = None, password: str | None = None):
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
    self.logger.info(f'Loading wakeword config from {config_file}')
    with open(config_file, encoding = 'utf-8') as file:
      config_content = json.load(file)
      assert isinstance(config_content, dict)
      for language, locale_config in config_content.items():
        self.logger.info(f'Loading wakeword config for language "{language}"')
        self.config[language] = WakewordSetting(**locale_config)

  def _handle_connection_close(self, websocket: websockets.legacy.server.WebSocketServerProtocol, exception: websockets.exceptions.ConnectionClosedOK):
    if exception.reason:
      self.logger.info(f'Connection closed {websocket.remote_address} with code {exception.code}. Reason: {exception.reason}')
    else:
      self.logger.info(f'Connection closed {websocket.remote_address} with code {exception.code}')

  async def _handle_detection_result(
    self,
    websocket: websockets.legacy.server.WebSocketServerProtocol,
    sound_name: str | None,
    score: float,
  ):
    if sound_name:
      sound = create_detected_sound_object(sound_name, score)
      message = json.dumps(sound)
      await websocket.send(message)

  async def _handle_client_requests(
    self,
    websocket: websockets.legacy.server.WebSocketServerProtocol,
    setting: WakewordSetting,
    request: InitMessage,
  ):
    started = False

    if 'wakeword-detection' in request.features:
      wakeword_engine = WakewordEngine(setting, self.logger)

    if 'sound-detection' in request.features:
      consumer = DetectorConsumer(self.detector, self.logger)

    try:
      event = {
        'type': 'init',
        'server': SERVER_HEADER,
        'status': 'ready',
        'languages': self.supported_languages,
      }

      await websocket.send(json.dumps(event))
      self.logger.info(f'Connection from {websocket.remote_address} {websocket.request_headers["User-Agent"]}')

      if 'wakeword-detection' in request.features:
        wakeword_engine.start_utt()

      started = True
      async for chunk in websocket:
        if 'wakeword-detection' in request.features:
          sound, score = await self._loop.run_in_executor(self.pool, wakeword_engine.process_raw, chunk)
          await self._handle_detection_result(websocket, sound, score)

          if sound:
            if 'sound-detection' in request.features:
              consumer.reset_buffer()
            continue

        if 'sound-detection' in request.features:
          sound, score = consumer.process_raw(chunk)
          await self._handle_detection_result(websocket, sound, score)
    except websockets.exceptions.ConnectionClosedOK as exception:
      self._handle_connection_close(websocket, exception)
    except Exception as exception:
      error_message = f'Invalid Message: {exception}'
      await websocket.close(code = 1003, reason = error_message)
      self.logger.error(error_message)
      if self.verbose:
        traceback.print_exc()
    finally:
      del consumer
      if started and 'wakeword-detection' in request.features:
        wakeword_engine.end_utt()

  async def _handler_client(self, websocket: websockets.legacy.server.WebSocketServerProtocol):
    init_timeout_timer_handler = self._loop.call_later(5, lambda: self._loop.create_task(
      websocket.close(code = 1002, reason = 'Init Timeout'),
      name = 'Init Timeout Task',
    ))

    try:
      message = await websocket.recv()
      init_timeout_timer_handler.cancel()
      data = json.loads(message)
      request = InitMessage(**data)
      wakeword_setting = self.config[request.language]

      await self._handle_client_requests(websocket, wakeword_setting, request)
    except (ValueError, TypeError):
      error_message = f'Invalid Init Message: {message}'
      self.logger.error(error_message)
      await websocket.close(code = 1003, reason = error_message)
    except websockets.exceptions.ConnectionClosedOK as exception:
      self._handle_connection_close(websocket, exception)
    except Exception as error:
      error_message = f'Unexpected Error: {error}'
      self.logger.error(error_message)
      await websocket.close(code = 4000, reason = error_message)
      if self.verbose:
        traceback.print_exc()

  async def listen(self, host: str, port: int) -> None:
    async with websockets.legacy.server.serve(self._handler_client, host, port, ssl = self.ssl_context, server_header = SERVER_HEADER, logger = self.logger):
      if self.on_listening:
        await self.on_listening()
      else:
        await asyncio.Future()
