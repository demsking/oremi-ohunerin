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
import concurrent.futures
import json
import logging
import os
import traceback
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlparse

from websockets.exceptions import ConnectionClosedError
from websockets.exceptions import ConnectionClosedOK
from websockets.http11 import Request
from websockets.http11 import Response

from ohunerin.core.package import APP_NAME
from ohunerin.core.package import APP_VERSION
from ohunerin.engines.detector import DetectorConsumer
from ohunerin.engines.detector import DetectorEngine
from ohunerin.engines.detector import recommended_num_threads
from ohunerin.engines.wakeword import WakewordEngine
from ohunerin.engines.wakeword import WakewordPool
from ohunerin.models.sound import create_detected_sound_object
from ohunerin.models.sound import DetectedSound
from ohunerin.models.sound import SoundsConfig
from ohunerin.models.sound import SoundType
from ohunerin.models.wakeword import WakewordsConfig
from ohunerin.models.wakeword import WakewordSetting
from ohunerin.server.http import HttpHandler
from ohunerin.server.websocket import BroadcastingWebSocketServer
from ohunerin.server.websocket import WebSocketConnection
from ohunerin.server.websocket import WebSocketServer

logger = logging.getLogger(__name__)

__all__ = [
  "BroadcastingWebSocketServer",
  "DetectedSound",
  "DetectorConsumer",
  "DetectorEngine",
  "Server",
  "WakewordEngine",
  "WakewordPool",
  "WakewordSetting",
  "WebSocketServer",
]

SERVER_NAME = f"{APP_NAME}/{APP_VERSION}"
MAX_REASON_LENGTH = 123

#: How long a connection waits for a wake-word decoder before being rejected.
#:
#: Decoders are checked out per connection, so the wait only absorbs the race
#: between a client connecting and another one releasing its decoder; a longer
#: wait would just delay the inevitable rejection.
WAKEWORD_DECODER_ACQUIRE_TIMEOUT = 1.0

BASE_DIR = Path(__file__).resolve().parents[2]

HTDOCS_DIR = BASE_DIR / "htdocs"
DOCUMENTATION_PATH = BASE_DIR / "DOCUMENTATION.md"
OPENAPI_PATH = HTDOCS_DIR / "openapi.json"
INDEX_PATH = HTDOCS_DIR / "index.html"

MODELS_DIR = BASE_DIR / "models"


class Server(WebSocketServer):
  """Main Ohunerin WebSocket server for ambient sound & wake word detection and HTTP docs."""

  def __init__(
    self,
    wakewords_config: WakewordsConfig,
    sounds_config: SoundsConfig,
    threshold: float,
    model: Path,
    *,
    wakeword_pool_size: int | None = None,
    cert_file: str | None = None,
    key_file: str | None = None,
    password: str | None = None,
  ) -> None:
    super().__init__(
      server_header=SERVER_NAME,
      cert_file=cert_file,
      key_file=key_file,
      password=password,
      process_request=self.process_http_request,
    )

    self.wakewords_config = wakewords_config
    self.sounds_config = sounds_config
    self.num_threads = os.cpu_count() or 1
    self.http_handler = HttpHandler(
      wakewords_config=wakewords_config,
      sounds_config=sounds_config,
      threshold=threshold,
      model=model,
      detector_threads=recommended_num_threads(),
      wakeword_pool_size=wakeword_pool_size,
    )

    self.pool = concurrent.futures.ThreadPoolExecutor(
      max_workers=self.num_threads,
      thread_name_prefix=APP_NAME,
    )

    self._loop = asyncio.get_running_loop()

  @property
  def supported_languages(self) -> list[str]:
    return self.http_handler.supported_languages

  @property
  def supported_sounds(self) -> list[str]:
    return self.http_handler.supported_sounds

  def get_wakeword_pool(self, language: str) -> WakewordPool:
    return self.http_handler.get_wakeword_pool(language)

  def get_detector_consumer(self) -> DetectorConsumer:
    return self.http_handler.get_detector_consumer()

  async def process_http_request(self, connection: WebSocketConnection, request: Request) -> Response | None:
    """Process incoming HTTP requests before WebSocket handshake."""
    return await self.http_handler.process_request(request)

  @staticmethod
  def truncate_reason(reason: str) -> str:
    if len(reason) > MAX_REASON_LENGTH:
      return reason[: MAX_REASON_LENGTH - 3] + "..."
    return reason

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
    message: bytes | str,
  ) -> None:
    pass

  def _parse_query_params(self, path: str) -> tuple[WakewordPool | None, DetectorConsumer | None]:
    parsed_url = urlparse(path)
    query_params = parse_qs(parsed_url.query)

    if "features" not in query_params:
      raise ValueError("features query parameter is required")

    features = []
    for f in query_params.get("features", []):
      features.extend([x.strip() for x in f.split(",") if x.strip()])

    if not features:
      raise ValueError("At least one feature must be specified in the features query parameter")

    language = query_params.get("language", [""])[0]

    wakeword_pool: WakewordPool | None = None
    detector_consumer: DetectorConsumer | None = None

    for feature_name in features:
      if feature_name == "wakeword-detection":
        if not language:
          raise ValueError("language query parameter is required for wakeword-detection")

        if language not in self.supported_languages:
          raise ValueError(f"Unsupported language: {language}")

        wakeword_pool = self.get_wakeword_pool(language)
      elif feature_name == "sound-detection":
        detector_consumer = self.get_detector_consumer()

    return wakeword_pool, detector_consumer

  async def _handle_audio_data(
    self,
    websocket: WebSocketConnection,
    wakeword_engine: WakewordEngine | None,
    detector_consumer: DetectorConsumer | None,
  ) -> None:
    user_agent = websocket.request.headers.get("User-Agent", "unknown") if websocket.request else "unknown"
    logger.info(f"Connection from {websocket.remote_address} {user_agent}")

    started = False

    try:
      if wakeword_engine:
        wakeword_engine.start_utt()

      started = True

      async for chunk in websocket:
        if wakeword_engine:
          sound, score = await self._loop.run_in_executor(self.pool, wakeword_engine.process_raw, chunk)  # type: ignore

          if sound:
            await self._handle_detection_result(websocket, "wakeword", sound, score)

            if detector_consumer:
              detector_consumer.reset_buffer()

            continue

        if detector_consumer:
          # TFLite inference takes milliseconds: run it in the executor so a
          # detection on one connection never stalls the event loop (and every
          # other connection) for the duration of the inference.
          sound, score = await self._loop.run_in_executor(self.pool, detector_consumer.process_raw, chunk)  # type: ignore

          if sound:
            await self._handle_detection_result(websocket, "sound", sound, score)
    except ConnectionClosedOK as exception:
      await self._handle_connection_close(websocket, exception)
    except ConnectionClosedError as exception:
      await self._handle_connection_close(websocket, exception)
    except Exception as exception:
      error_message = str(exception)
      await websocket.close(code=1003, reason=error_message)
      logger.error(error_message)

      if logger.isEnabledFor(logging.DEBUG):
        traceback.print_exc()
    else:
      # The asyncio implementation ends the message iterator on a normal closure
      # (1000, 1001) instead of raising ConnectionClosedOK like the legacy
      # implementation did, so the close is no longer observed as an exception.
      await self._handle_connection_close(websocket)
    finally:
      if detector_consumer:
        del detector_consumer

      if started and wakeword_engine:
        wakeword_engine.end_utt()
        del wakeword_engine

  async def _handle_messages(self, websocket: WebSocketConnection) -> None:
    request_path = websocket.request.path if websocket.request else ""
    parsed_url = urlparse(request_path)

    if parsed_url.path != "/ws":
      error_message = f"Only '/ws' endpoint is supported, but received '{parsed_url.path}'"
      logger.error(error_message)
      await websocket.close(code=1008, reason=Server.truncate_reason(error_message))
      return

    try:
      wakeword_pool, detector_consumer = self._parse_query_params(request_path)
    except Exception as exception:
      error_message = f"Failed to parse query parameters: {exception}"
      logger.error(error_message)
      await websocket.close(code=1003, reason=Server.truncate_reason(error_message))
      return

    if wakeword_pool is None and detector_consumer is None:
      await websocket.close(
        1003,
        "No feature provided in the query parameters, which is required to start listening",
      )
      return

    wakeword_engine: WakewordEngine | None = None

    try:
      if wakeword_pool is not None:
        # One decoder per connection: PocketSphinx cannot multiplex the open
        # utterance, so a shared decoder makes concurrent clients collide on
        # start_utt() and reset each other's audio. Building a decoder costs
        # ~80-200 ms, hence the thread hop.
        wakeword_engine = await asyncio.to_thread(wakeword_pool.acquire, WAKEWORD_DECODER_ACQUIRE_TIMEOUT)

        if wakeword_engine is None:
          error_message = "No wake-word decoder available on this server, try again later"
          logger.warning(error_message)
          await websocket.close(code=1013, reason=Server.truncate_reason(error_message))
          return

      await self._handle_audio_data(websocket, wakeword_engine, detector_consumer)
    except Exception as exception:
      error_message = f"Unexpected error: {exception}"
      logger.error(error_message)
      await websocket.close(code=1003, reason=Server.truncate_reason(error_message))
    finally:
      if wakeword_pool is not None and wakeword_engine is not None:
        # Resets the native utterance and hands the decoder back to the pool.
        wakeword_pool.release(wakeword_engine)
