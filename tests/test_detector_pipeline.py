# Copyright 2026 Sébastien Demanou. All Rights Reserved.
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
import concurrent.futures
import json
import logging
import os
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio
from websockets.datastructures import Headers
from websockets.http11 import Request

from ohunerin.audio.processing import to_ndarray
from ohunerin.core.package import APP_VERSION
from ohunerin.engines.detector import DEFAULT_MAX_INFERENCE_THREADS
from ohunerin.engines.detector import DetectorConsumer
from ohunerin.engines.detector import DetectorEngine
from ohunerin.engines.detector import recommended_num_threads
from ohunerin.engines.detector import WINDOW_BYTES
from ohunerin.engines.wakeword import WakewordEngine
from ohunerin.models.sound import SoundsConfig
from ohunerin.models.wakeword import DictionaryEntry
from ohunerin.models.wakeword import WakewordSetting
from ohunerin.models.wakeword import WakewordsConfig
from ohunerin.server import Server

# These tests load the real yamnet.tflite model; run ./scripts/install-model.sh
# first, exactly like the rest of the suite.


class RecordingDetector:
  """Duck-typed DetectorEngine that records the windows it is asked to classify."""

  def __init__(self) -> None:
    self.windows: list[bytes] = []

  def classify_window(self, audio_array: np.ndarray) -> tuple[str | None, float]:
    # Normalization divides by a power of two, so the int16 round-trip is exact.
    self.windows.append((audio_array[:, 0] * 32768.0).astype(np.int16).tobytes())
    return None, 0.0


def legacy_process_raw(buffer: bytearray, index: int, chunk: bytes) -> tuple[int, bytes | None]:
  """Reference implementation of the historical byte-by-byte buffering."""
  for byte in chunk:
    buffer[index] = byte
    index += 1

    if index == WINDOW_BYTES:
      return 0, bytes(buffer)

  return index, None


@pytest.fixture
def logger():
  return logging.getLogger("test_detector_pipeline")


@pytest.fixture
def data_path():
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  return os.path.join(base_dir, "models", "yamnet.tflite")


@pytest.fixture
def raw_config():
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

  with open(os.path.join(base_dir, "config.json"), encoding="utf-8") as file:
    return json.load(file)


@pytest.fixture
def engine(data_path):
  return DetectorEngine(data_path, score_threshold=0.1, num_threads=2)


@pytest_asyncio.fixture
async def server(raw_config, data_path):
  wakewords_config = WakewordsConfig.model_validate(raw_config.get("wakewords", []))
  sounds_config = SoundsConfig.model_validate(raw_config.get("sounds", {}))

  return Server(
    wakewords_config=wakewords_config,
    sounds_config=sounds_config,
    threshold=0.65,
    model=Path(data_path),
  )


def test_recommended_num_threads_is_bounded():
  threads = recommended_num_threads()

  assert 1 <= threads <= DEFAULT_MAX_INFERENCE_THREADS


def test_process_raw_matches_legacy_byte_loop():
  chunks = [
    bytes(range(100)),
    b"\x01" * 8000,
    b"\x02" * 15600,
    b"\x03" * 7777,
    b"",
    b"\x04" * 300,
  ]

  recording = RecordingDetector()
  consumer = DetectorConsumer(recording)  # type: ignore[arg-type]

  legacy_buffer = bytearray(WINDOW_BYTES)
  legacy_index = 0
  legacy_windows: list[bytes] = []

  for chunk in chunks:
    legacy_index, window = legacy_process_raw(legacy_buffer, legacy_index, chunk)

    if window is not None:
      legacy_windows.append(window)

    sound, score = consumer.process_raw(chunk)
    assert sound is None
    assert score == 0.0

  assert consumer._buffer_index == legacy_index
  assert recording.windows == legacy_windows


def test_process_raw_keeps_partial_frames_across_chunks():
  recording = RecordingDetector()
  consumer = DetectorConsumer(recording)  # type: ignore[arg-type]

  consumer.process_raw(b"\x01" * (WINDOW_BYTES - 10))
  assert consumer._buffer_index == WINDOW_BYTES - 10
  assert recording.windows == []

  consumer.process_raw(b"\x02" * 10)
  assert consumer._buffer_index == 0
  assert len(recording.windows) == 1
  assert recording.windows[0][: WINDOW_BYTES - 10] == b"\x01" * (WINDOW_BYTES - 10)
  assert recording.windows[0][WINDOW_BYTES - 10 :] == b"\x02" * 10


def test_classify_window_is_thread_safe(engine):
  window = to_ndarray(b"\x00" * WINDOW_BYTES, 1)

  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(lambda _: engine.classify_window(window), range(8)))

  assert len(results) == 8
  # Concurrent calls must not interleave in the shared TensorAudio buffer.
  assert len({result[0] for result in results}) == 1


@pytest.mark.asyncio
async def test_sound_consumers_are_per_connection(server):
  first = server._parse_query_params("/ws?features=sound-detection")[1]  # type: ignore
  second = server._parse_query_params("/ws?features=sound-detection")[1]  # type: ignore

  assert first is not None
  assert second is not None
  assert first is not second
  assert first._detector is second._detector  # the engine itself stays shared

  first.process_raw(b"\x01" * 50)
  assert first._buffer_index == 50
  assert second._buffer_index == 0


@pytest.mark.asyncio
async def test_detector_threads_are_bounded_on_the_server(server):
  assert server.http_handler.detector_threads <= DEFAULT_MAX_INFERENCE_THREADS


@pytest.mark.asyncio
async def test_openapi_body_is_cached(server):
  first = server.http_handler.get_openapi_body()
  second = server.http_handler.get_openapi_body()

  assert first is second
  assert APP_VERSION.encode() in first

  response = await server.process_http_request(None, Request("/openapi.json", Headers()))
  assert response is not None
  assert response.body == first


def test_wakeword_engine_serializes_decoder_access(data_path):
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  setting = WakewordSetting(
    model=os.path.join(base_dir, "models", "wakeword-en", "acoustic-model"),
    dictionary=os.path.join(base_dir, "models", "wakeword-en", "pronounciation-dictionary.dict"),
    wakewords=[DictionaryEntry(word="oremi", phones=["oo rr ei mm ii"])],
    discriminants=[],
  )
  engine = WakewordEngine(setting)
  engine.start_utt()

  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(lambda _: engine.process_raw(b"\x00" * 8000), range(4)))

  engine.end_utt()

  assert all(sound is None for sound, _ in results)
