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
import http
import json
import logging
import os
import traceback
from collections import defaultdict
from functools import lru_cache
from itertools import chain
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlparse

import websockets.datastructures
import websockets.exceptions
import websockets.legacy.protocol
from oremi_core.wsserver import WebSocketConnection
from oremi_core.wsserver import WebSocketServer

from .detector import DetectorConsumer
from .detector import DetectorEngine
from .models import create_detected_sound_object
from .models import DetectedSound
from .models import DictionaryEntry
from .models import OhunerinConfig
from .models import SoundType
from .models import WakewordEntry
from .models import WakewordSetting
from .package import APP_NAME
from .package import APP_VERSION
from .wakeword import WakewordEngine

__all__ = [
  "DetectedSound",
  "DetectorConsumer",
  "DetectorEngine",
  "Server",
  "WakewordEngine",
  "WakewordSetting",
]


SERVER_NAME = f"{APP_NAME}/{APP_VERSION}"
MAX_REASON_LENGTH = 123


BASE_DIR = Path(__file__).resolve().parent

DOC_DIR = BASE_DIR / "doc"
DOCUMENTATION_PATH = BASE_DIR / "DOCUMENTATION.md"
OPENAPI_PATH = DOC_DIR / "openapi.json"
INDEX_PATH = DOC_DIR / "index.html"

MODELS_DIR = BASE_DIR / "models"


# Default acoustic-model and dictionary paths per language (relative to the package dir).
LANGUAGE_MODEL_PATHS: dict[str, tuple[str, str]] = {
  "fr": (
    "wakeword-fr/cmusphinx-fr-ptm-8khz-5.2",
    "wakeword-fr/pronounciation-dictionary.dict",
  ),
  "en": (
    "wakeword-en/acoustic-model",
    "wakeword-en/pronounciation-dictionary.dict",
  ),
}


class Server(WebSocketServer):
  def __init__(
    self,
    *,
    config: OhunerinConfig,
    model_path: str | None = None,
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
      process_request=self.process_http_request,
    )
    self.verbose = logger.isEnabledFor(logging.DEBUG)
    self.config: OhunerinConfig = config
    self.num_threads = os.cpu_count() or 1
    self.model_path = model_path or os.path.join(os.path.dirname(__file__), "models", "yamnet.tflite")

    self.pool = concurrent.futures.ThreadPoolExecutor(
      max_workers=self.num_threads,
      thread_name_prefix=APP_NAME,
    )

    self._loop = asyncio.get_running_loop()

  async def process_http_request(
    self, path: str, request_headers: websockets.datastructures.Headers
  ) -> tuple[http.HTTPStatus, list[tuple[str, str]], bytes] | None:
    """Process incoming HTTP requests before WebSocket handshake, serving documentation and OpenAPI files."""
    clean_path = path.split("?")[0]

    if clean_path == "/openapi.json":
      self.logger.info(f"Serving OpenAPI JSON for HTTP request from {request_headers.get('User-Agent', 'unknown')}")
      body = json.dumps(self.get_openapi_spec(), ensure_ascii=False).encode("utf-8")
      headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
      ]

      return http.HTTPStatus.OK, headers, body

    if clean_path == "/docs":
      self.logger.info(f"Serving API documentation HTML for HTTP request from {request_headers.get('User-Agent', 'unknown')}")
      html_content = self.get_index_html()
      body = html_content.encode("utf-8")
      headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(body))),
      ]

      return http.HTTPStatus.OK, headers, body

    if clean_path == "/info":
      self.logger.info(f"Serving server info for HTTP request from {request_headers.get('User-Agent', 'unknown')}")

      body = json.dumps(self.get_server_info(), ensure_ascii=False).encode("utf-8")
      headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
      ]

      return http.HTTPStatus.OK, headers, body

    if clean_path == "/":
      self.logger.info(f"Redirecting root path to /info for HTTP request from {request_headers.get('User-Agent', 'unknown')}")

      body = b""
      headers = [
        ("Location", "/info"),
        ("Content-Length", "0"),
      ]

      return http.HTTPStatus.FOUND, headers, body

    if clean_path == "/ws":
      return None

    # Reject any other path with 404 Not Found
    body = b"Not Found"
    headers = [
      ("Content-Type", "text/plain; charset=utf-8"),
      ("Content-Length", str(len(body))),
    ]
    return http.HTTPStatus.NOT_FOUND, headers, body

  def get_server_info(self) -> dict:
    """Return information about the server."""
    return {
      "name": APP_NAME,
      "version": APP_VERSION,
      "threshold": self.config.threshold,
      "wakewords": self.supported_wakewords,
      "sounds": self.config.sounds,
    }

  def get_documentation(self) -> str:
    """Read the DOCUMENTATION.md markdown content from the project root."""
    with open(DOCUMENTATION_PATH, encoding="utf-8") as f:
      return f.read()

  def get_openapi_spec(self) -> dict:
    """Generate the OpenAPI specification by loading the external openapi.json template."""
    with open(OPENAPI_PATH, encoding="utf-8") as f:
      spec = json.load(f)

    spec["info"]["description"] = self.get_documentation()
    spec["info"]["version"] = APP_VERSION

    return spec

  def get_index_html(self) -> str:
    """Generate the Scalar HTML markup by loading the external index.html template."""
    with open(INDEX_PATH, encoding="utf-8") as index_file:
      return index_file.read()

  @property
  def supported_wakewords(self):
    result: dict[str, list[str]] = defaultdict(list)

    for entry in self.config.wakewords:
      result[entry.language].append(entry.word)

    return result

  @property
  def supported_languages(self) -> list[str]:
    return list(self.supported_wakewords.keys())

  def get_wakewords_by_language(self, language: str) -> list[WakewordEntry]:
    return [entry for entry in self.config.wakewords if entry.language == language]

  @lru_cache
  def get_wakeword_engine(self, language: str) -> WakewordEngine:
    model_rel, dict_rel = LANGUAGE_MODEL_PATHS.get(
      language,
      (f"wakeword-{language}/acoustic-model", f"wakeword-{language}/pronounciation-dictionary.dict"),
    )

    model_path = MODELS_DIR / model_rel
    dict_path = MODELS_DIR / dict_rel

    wakewords = self.get_wakewords_by_language(language)

    self.logger.info(f'Loading wakeword config for language "{language}": {[w.word for w in wakewords]}')
    wakewords = WakewordSetting(
      model=str(model_path),
      dictionary=str(dict_path),
      wakewords=[DictionaryEntry(word=entry.word, phones=entry.phones) for entry in wakewords],
      discriminants=list(chain.from_iterable([entry.discriminants for entry in wakewords])),
    )

    return WakewordEngine(wakewords, self.logger)

  @lru_cache
  def get_detector_consumer(self) -> DetectorConsumer:
    detector = DetectorEngine(
      model=self.model_path,
      score_threshold=self.config.threshold,
      num_threads=self.num_threads,
      logger=self.logger,
      allowlist=self.config.sounds,
    )

    return DetectorConsumer(detector, logger=self.logger)

  @staticmethod
  def truncate_reason(reason: str) -> str:
    if len(reason) > MAX_REASON_LENGTH:
      return reason[: MAX_REASON_LENGTH - 3] + "..."
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

  def _handle_connection_close(
    self,
    websocket: WebSocketConnection,
    exception: websockets.exceptions.ConnectionClosedOK | websockets.exceptions.ConnectionClosedError,
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

  def _parse_query_params(self, path: str) -> tuple[WakewordEngine | None, DetectorConsumer | None]:
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

    wakeword_engine: WakewordEngine | None = None
    detector_consumer: DetectorConsumer | None = None

    for feature_name in features:
      if feature_name == "wakeword-detection":
        if not language:
          raise ValueError("language query parameter is required for wakeword-detection")

        if language not in self.supported_languages:
          raise ValueError(f"Unsupported language: {language}")

        wakeword_engine = self.get_wakeword_engine(language)
      elif feature_name == "sound-detection":
        detector_consumer = self.get_detector_consumer()

    return wakeword_engine, detector_consumer

  async def _handle_audio_data(
    self,
    websocket: WebSocketConnection,
    wakeword_engine: WakewordEngine | None,
    detector_consumer: DetectorConsumer | None,
  ) -> None:
    self.logger.info(f"Connection from {websocket.remote_address} {websocket.request_headers.get('User-Agent', '')}")

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
          sound, score = detector_consumer.process_raw(chunk)  # type: ignore

          if sound:
            await self._handle_detection_result(websocket, "sound", sound, score)
    except websockets.exceptions.ConnectionClosedOK as exception:
      self._handle_connection_close(websocket, exception)
    except websockets.exceptions.ConnectionClosedError as exception:
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
    parsed_url = urlparse(websocket.path)

    if parsed_url.path != "/ws":
      error_message = f"Only '/ws' endpoint is supported, but received '{parsed_url.path}'"
      self.logger.error(error_message)
      await websocket.close(code=1008, reason=Server.truncate_reason(error_message))
      return

    try:
      wakeword_engine, detector_consumer = self._parse_query_params(websocket.path)
    except Exception as exception:
      error_message = f"Failed to parse query parameters: {exception}"
      self.logger.error(error_message)
      await websocket.close(code=1003, reason=Server.truncate_reason(error_message))
      return

    if wakeword_engine is None and detector_consumer is None:
      await websocket.close(
        websockets.legacy.protocol.CloseCode.INVALID_DATA,
        "No feature provided in the query parameters, which is required to start listening",
      )
      return

    try:
      await self._handle_audio_data(websocket, wakeword_engine, detector_consumer)
    except Exception as exception:
      error_message = f"Unexpected error: {exception}"
      self.logger.error(error_message)
      await websocket.close(code=1003, reason=Server.truncate_reason(error_message))
