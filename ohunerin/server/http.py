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
import http
import json
import logging
import os
from collections import defaultdict
from functools import lru_cache
from itertools import chain
from pathlib import Path
from typing import Any

import websockets.datastructures

from ohunerin.core.logger import LOGGER_DATE_FORMAT
from ohunerin.core.package import APP_NAME
from ohunerin.core.package import APP_VERSION
from ohunerin.core.package import HTDOCS_DIR
from ohunerin.core.package import MODELS_DIR
from ohunerin.core.package import PROJECT_DIRECTORY
from ohunerin.engines.detector import DetectorConsumer
from ohunerin.engines.detector import DetectorEngine
from ohunerin.engines.wakeword import WakewordEngine
from ohunerin.models.sound import SoundsConfig
from ohunerin.models.wakeword import DictionaryEntry
from ohunerin.models.wakeword import WakewordEntry
from ohunerin.models.wakeword import WakewordsConfig
from ohunerin.models.wakeword import WakewordSetting

logger = logging.getLogger(__name__)
_http_logger = logging.getLogger(__name__)

_handler = logging.StreamHandler()
_http_fmt = logging.Formatter(f"%(asctime)s - {APP_NAME} - HTTP - %(message)s", datefmt=LOGGER_DATE_FORMAT)
_handler.setFormatter(_http_fmt)

_http_logger.addHandler(_handler)
_http_logger.setLevel(logging.INFO)
_http_logger.propagate = False

DOCUMENTATION_PATH = PROJECT_DIRECTORY / "DOCUMENTATION.md"
OPENAPI_PATH = HTDOCS_DIR / "openapi.json"
INDEX_PATH = HTDOCS_DIR / "index.html"

SERVICE_DESCRIPTION = DOCUMENTATION_PATH.read_text(encoding="utf-8")


# Default acoustic-model and dictionary paths per language (relative to package dir)
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


class HttpHandler:
  """HTTP request handler serving documentation, OpenAPI specifications, and model lists."""

  def __init__(
    self,
    wakewords_config: WakewordsConfig,
    sounds_config: SoundsConfig,
    threshold: float,
    model: Path,
    num_threads: int | None = None,
  ) -> None:
    self.wakewords_config = wakewords_config
    self.sounds_config = sounds_config
    self.threshold = threshold
    self.model = model
    self.num_threads = num_threads or (os.cpu_count() or 1)

  def _send(
    self,
    method: str,
    path: str,
    version: str,
    status: http.HTTPStatus,
    headers: list[tuple[str, str]],
    body: bytes,
  ) -> tuple[http.HTTPStatus, list[tuple[str, str]], bytes]:
    _http_logger.info(f"{method} {path} {version} {status.value} {status.phrase}")

    return status, headers, body

  async def process_request(
    self, path: str, request_headers: websockets.datastructures.Headers
  ) -> tuple[http.HTTPStatus, list[tuple[str, str]], bytes] | None:
    """Process incoming HTTP request prior to WebSocket handshake."""
    clean_path = path.split("?")[0]
    method = request_headers.get("Method", "GET")
    version = request_headers.get("Version", "HTTP/1.1")

    if clean_path == "/":
      headers = [
        ("Location", "/health"),
        ("Content-Length", "0"),
      ]

      return self._send(method, path, version, http.HTTPStatus.FOUND, headers, b"")

    if clean_path == "/health":
      body = json.dumps(self.get_server_info(), ensure_ascii=False).encode("utf-8")
      headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
      ]

      return self._send(method, path, version, http.HTTPStatus.OK, headers, body)

    if clean_path == "/openapi.json":
      body = json.dumps(self.get_openapi_spec(), ensure_ascii=False).encode("utf-8")
      headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
      ]

      return self._send(method, path, version, http.HTTPStatus.OK, headers, body)

    if clean_path == "/docs":
      body = self.get_index_html().encode("utf-8")
      headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(body))),
      ]

      return self._send(method, path, version, http.HTTPStatus.OK, headers, body)

    if clean_path == "/api/sounds":
      body = json.dumps(self.supported_sounds, ensure_ascii=False).encode("utf-8")
      headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
      ]

      return self._send(method, path, version, http.HTTPStatus.OK, headers, body)

    if clean_path == "/ws":
      return None

    body = b"Not Found"
    headers = [
      ("Content-Type", "text/plain; charset=utf-8"),
      ("Content-Length", str(len(body))),
    ]

    return self._send(method, path, version, http.HTTPStatus.NOT_FOUND, headers, body)

  def get_server_info(self) -> dict[str, Any]:
    """Return information about the server."""
    return {
      "name": APP_NAME,
      "version": APP_VERSION,
      "threshold": self.threshold,
      "wakewords": self.supported_wakewords,
      "sounds": self.sounds_config.model_dump(),
    }

  def get_openapi_spec(self) -> dict[str, Any]:
    """Generate OpenAPI specification object with updated documentation and version."""
    openapi: dict[str, Any] = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))

    openapi["info"]["description"] = SERVICE_DESCRIPTION
    openapi["info"]["version"] = APP_VERSION

    return openapi

  def get_index_html(self) -> str:
    """Read Scalar documentation index.html template."""
    return INDEX_PATH.read_text()

  @property
  def supported_wakewords(self) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)

    for entry in self.wakewords_config.wakewords:
      result[entry.language].append(entry.word)

    return result

  @property
  def supported_languages(self) -> list[str]:
    return list(self.supported_wakewords.keys())

  @property
  def supported_sounds(self) -> list[str]:
    return self.sounds_config.effective_allowlist

  def get_wakewords_by_language(self, language: str) -> list[WakewordEntry]:
    return [entry for entry in self.wakewords_config.wakewords if entry.language == language]

  @lru_cache
  def get_wakeword_engine(self, language: str) -> WakewordEngine:
    model_rel, dict_rel = LANGUAGE_MODEL_PATHS.get(
      language,
      (f"wakeword-{language}/acoustic-model", f"wakeword-{language}/pronounciation-dictionary.dict"),
    )

    model_path = MODELS_DIR / model_rel
    dict_path = MODELS_DIR / dict_rel

    wakewords = self.get_wakewords_by_language(language)

    logger.info(f'Loading wakeword config for language "{language}": {[w.word for w in wakewords]}')
    setting = WakewordSetting(
      model=str(model_path),
      dictionary=str(dict_path),
      wakewords=[DictionaryEntry(word=entry.word, phones=entry.phones) for entry in wakewords],
      discriminants=list(chain.from_iterable([entry.discriminants for entry in wakewords])),
    )

    return WakewordEngine(setting)

  @lru_cache
  def get_detector_consumer(self) -> DetectorConsumer:
    detector = DetectorEngine(
      model=self.model,
      score_threshold=self.threshold,
      num_threads=self.num_threads,
      allowlist=self.sounds_config.allowlist,
      denylist=self.sounds_config.denylist,
    )

    return DetectorConsumer(detector)
