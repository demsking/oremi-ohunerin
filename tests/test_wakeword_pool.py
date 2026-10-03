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
import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio

from ohunerin.engines.wakeword import WakewordPool
from ohunerin.models.sound import SoundsConfig
from ohunerin.models.wakeword import DictionaryEntry
from ohunerin.models.wakeword import WakewordsConfig
from ohunerin.models.wakeword import WakewordSetting
from ohunerin.server import Server

# These tests load the real CMU Sphinx models; run ./scripts/install-model.sh
# first, exactly like the rest of the suite.

BASE_DIR = Path(__file__).resolve().parents[1]


class MockWebSocket:
  def __init__(self, path="/ws", chunks=None):
    self.path = path
    self.remote_address = ("127.0.0.1", 12345)
    self.request_headers = {"User-Agent": "MockClient"}
    self.chunks = chunks or []
    self.index = 0
    self.sent_messages = []
    self.closed_code = None
    self.closed_reason = None

  def __aiter__(self):
    return self

  async def __anext__(self):
    if self.index >= len(self.chunks):
      raise StopAsyncIteration
    chunk = self.chunks[self.index]
    self.index += 1
    return chunk

  async def send(self, message):
    self.sent_messages.append(message)

  async def close(self, code, reason=""):
    self.closed_code = code
    self.closed_reason = reason


@pytest.fixture
def logger():
  return logging.getLogger("test_wakeword_pool")


@pytest.fixture
def en_setting() -> WakewordSetting:
  return WakewordSetting(
    model=os.path.join(str(BASE_DIR), "models/wakeword-en/acoustic-model"),
    dictionary=os.path.join(str(BASE_DIR), "models/wakeword-en/pronounciation-dictionary.dict"),
    wakewords=[DictionaryEntry(word="oremi", phones=["OW R EH M IY"])],
    discriminants=[DictionaryEntry(word="remi", phones=["R EH M IY"])],
  )


@pytest_asyncio.fixture
async def make_server():
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

  with open(os.path.join(base_dir, "config.json"), encoding="utf-8") as file:
    raw = json.load(file)

  wakewords_config = WakewordsConfig.model_validate(raw.get("wakewords", []))
  sounds_config = SoundsConfig.model_validate(raw.get("sounds", {}))

  def factory(**kwargs) -> Server:
    return Server(
      wakewords_config=wakewords_config,
      sounds_config=sounds_config,
      threshold=0.65,
      model=Path(os.path.join("models", "yamnet.tflite")),
      **kwargs,
    )

  return factory


def test_acquire_returns_a_distinct_decoder_per_connection(en_setting):
  pool = WakewordPool(en_setting, size=3)
  engines = [pool.acquire(timeout=0) for _ in range(3)]

  assert all(engine is not None for engine in engines)
  assert len({id(engine) for engine in engines}) == 3
  assert pool.created == 3
  assert pool.in_use == 3
  assert pool.available == 0


def test_pool_never_builds_more_than_its_size(en_setting):
  pool = WakewordPool(en_setting, size=2)
  first = pool.acquire(timeout=0)
  second = pool.acquire(timeout=0)

  assert first is not None
  assert second is not None
  assert pool.acquire(timeout=0) is None
  assert pool.created == 2


def test_waiting_acquire_returns_a_released_decoder(en_setting):
  pool = WakewordPool(en_setting, size=1)
  held = pool.acquire(timeout=0)

  def release_later() -> None:
    time.sleep(0.1)
    pool.release(held)

  thread = threading.Thread(target=release_later)
  thread.start()

  reused = pool.acquire(timeout=5)
  thread.join()

  assert reused is held
  assert pool.created == 1


def test_release_is_idempotent(en_setting):
  pool = WakewordPool(en_setting, size=1)
  engine = pool.acquire(timeout=0)

  pool.release(engine)
  pool.release(engine)

  assert pool.available == 1
  assert pool.in_use == 0


def test_released_decoder_starts_a_clean_utterance(en_setting):
  pool = WakewordPool(en_setting, size=1)
  engine = pool.acquire(timeout=0)
  assert engine is not None

  engine.start_utt()
  pool.release(engine)

  reused = pool.acquire(timeout=0)
  assert reused is engine

  # A reused decoder must be able to open a new utterance; this used to raise
  # RuntimeError("Failed to start utterance processing") when two connections
  # shared one process-wide decoder.
  reused.start_utt()
  reused.end_utt()
  pool.release(reused)


def test_concurrent_connections_have_independent_utterances(en_setting):
  """Regression: one shared decoder made the second connection collide."""
  pool = WakewordPool(en_setting, size=2)
  first = pool.acquire(timeout=0)
  second = pool.acquire(timeout=0)

  assert first is not None
  assert second is not None
  assert first is not second

  first.start_utt()
  second.start_utt()

  assert first.process_raw(b"\x00" * 8000) == (None, 0.0)
  assert second.process_raw(b"\x00" * 8000) == (None, 0.0)

  pool.release(first)
  pool.release(second)

  assert pool.in_use == 0
  assert pool.available == 2


@pytest.mark.asyncio
async def test_two_concurrent_wakeword_sessions_both_get_a_decoder(make_server):
  server = make_server(wakeword_pool_size=2)
  pool = server.get_wakeword_pool("en")
  acquired: list = []
  ready = asyncio.Event()
  observed: dict = {}

  async def fake_handle_audio_data(websocket, wakeword_engine, detector_consumer):
    acquired.append(wakeword_engine)

    if len(acquired) == 2:
      observed["in_use"] = pool.in_use
      ready.set()

    await ready.wait()

  websockets = [MockWebSocket("/ws?features=wakeword-detection&language=en") for _ in range(2)]

  with patch.object(server, "_handle_audio_data", side_effect=fake_handle_audio_data):
    await asyncio.gather(*(server._handle_messages(websocket) for websocket in websockets))

  assert observed["in_use"] == 2
  assert acquired[0] is not acquired[1]
  assert pool.in_use == 0
  assert all(websocket.closed_code is None for websocket in websockets)


@pytest.mark.asyncio
async def test_server_rejects_a_wakeword_session_when_the_pool_is_exhausted(make_server):
  server = make_server(wakeword_pool_size=1)
  pool = server.get_wakeword_pool("en")
  held = pool.acquire(timeout=0)
  assert held is not None

  websocket = MockWebSocket("/ws?features=wakeword-detection&language=en")

  with patch("ohunerin.server.WAKEWORD_DECODER_ACQUIRE_TIMEOUT", 0.05):
    await server._handle_messages(websocket)

  assert websocket.closed_code == 1013
  assert "No wake-word decoder available" in websocket.closed_reason

  pool.release(held)
  assert pool.in_use == 0


@pytest.mark.asyncio
async def test_wakeword_pool_is_cached_per_language(make_server):
  server = make_server()

  assert server.get_wakeword_pool("en") is server.get_wakeword_pool("en")
  assert server.get_wakeword_pool("en") is not server.get_wakeword_pool("fr")
