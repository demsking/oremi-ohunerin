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
import json
import logging
import os
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import pytest_asyncio

from pathlib import Path

from ohunerin.models.sound import SoundsConfig
from ohunerin.models.wakeword import WakewordsConfig
from ohunerin.server import Server


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
  return logging.getLogger("test_server_audio_loop")


@pytest_asyncio.fixture
async def server(logger):
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  config_file = os.path.join(base_dir, "config.json")
  model_file = os.path.join("models", "yamnet.tflite")

  with open(config_file, encoding="utf-8") as f:
    raw = json.load(f)
  wakewords_config = WakewordsConfig.model_validate(raw.get("wakewords", []))
  sounds_config = SoundsConfig.model_validate(raw.get("sounds", {}))

  return Server(wakewords_config=wakewords_config, sounds_config=sounds_config, threshold=0.65, model=Path(model_file))


@pytest.mark.asyncio
async def test_handle_audio_data_wakeword_detection(server):
  mock_wakeword = MagicMock()
  # First chunk returns no detection, second chunk detects "oremi"
  mock_wakeword.process_raw.side_effect = [(None, 0.0), ("oremi", 0.95)]

  websocket = MockWebSocket(chunks=[b"\x00" * 100, b"\x00" * 100])

  await server._handle_audio_data(websocket, mock_wakeword, None)  # type: ignore

  assert mock_wakeword.start_utt.called
  assert mock_wakeword.end_utt.called

  # Ensure one detection result was sent
  assert len(websocket.sent_messages) == 1
  data = json.loads(websocket.sent_messages[0])
  assert data["type"] == "wakeword"
  assert data["sound"] == "oremi"
  assert data["score"] == 0.95


@pytest.mark.asyncio
async def test_handle_audio_data_sound_detection(server):
  mock_detector = MagicMock()
  mock_detector.process_raw.side_effect = [(None, 0.0), ("bark", 0.85)]

  websocket = MockWebSocket(chunks=[b"\x00" * 100, b"\x00" * 100])

  await server._handle_audio_data(websocket, None, mock_detector)  # type: ignore

  assert len(websocket.sent_messages) == 1
  data = json.loads(websocket.sent_messages[0])
  assert data["type"] == "sound"
  assert data["sound"] == "bark"
  assert data["score"] == 0.85


@pytest.mark.asyncio
async def test_handle_audio_data_exception(server):
  mock_detector = MagicMock()
  # Simulate unexpected error during processing
  mock_detector.process_raw.side_effect = RuntimeError("Processing error")

  websocket = MockWebSocket(chunks=[b"\x00" * 100])

  await server._handle_audio_data(websocket, None, mock_detector)  # type: ignore

  # Ensure connection was closed with code 1003
  assert websocket.closed_code == 1003
  assert "Processing error" in websocket.closed_reason  # type: ignore


@pytest.mark.asyncio
async def test_handle_messages_invalid_path(server):
  websocket = MockWebSocket(path="/invalid_endpoint")
  await server._handle_messages(websocket)  # type: ignore

  assert websocket.closed_code == 1008
  assert "Only '/ws' endpoint is supported" in websocket.closed_reason  # type: ignore


@pytest.mark.asyncio
async def test_handle_messages_invalid_params(server):
  # wakeword-detection without language raises ValueError
  websocket = MockWebSocket(path="/ws?features=wakeword-detection")
  await server._handle_messages(websocket)  # type: ignore

  assert websocket.closed_code == 1003
  assert "Failed to parse query parameters" in websocket.closed_reason  # type: ignore


@pytest.mark.asyncio
async def test_handle_messages_no_features(server):
  # When no features are provided, it should fail since features is required.
  websocket = MockWebSocket(path="/ws")
  await server._handle_messages(websocket)  # type: ignore

  assert websocket.closed_code == 1003
  assert "features query parameter is required" in websocket.closed_reason  # type: ignore


@pytest.mark.asyncio
async def test_handle_messages_invalid_features(server):
  # When invalid features are provided, it doesn't default, and since no valid features are enabled,
  # it should fail with "No feature provided".
  websocket = MockWebSocket(path="/ws?features=invalid")
  await server._handle_messages(websocket)  # type: ignore

  assert websocket.closed_code is not None
  assert "No feature provided in the query parameters" in websocket.closed_reason  # type: ignore


@pytest.mark.asyncio
async def test_handle_messages_default_features_valid(server):
  # When no features are provided but language is, it should still fail because features is required
  websocket = MockWebSocket(path="/ws?language=fr", chunks=[b"\x00" * 100])
  await server._handle_messages(websocket)  # type: ignore

  assert websocket.closed_code == 1003
  assert "features query parameter is required" in websocket.closed_reason  # type: ignore


@pytest.mark.asyncio
async def test_handle_messages_valid_flow(server):
  websocket = MockWebSocket(path="/ws?features=sound-detection&allowlist=Dog", chunks=[b"\x00" * 100])

  async def mock_handle_audio_fn(ws, ww, dc):
    pass

  with patch.object(server, "_handle_audio_data", side_effect=mock_handle_audio_fn) as mock_handle_audio:
    await server._handle_messages(websocket)  # type: ignore
    mock_handle_audio.assert_called_once()

    # Verify mock_handle_audio arguments
    args, _kwargs = mock_handle_audio.call_args
    assert args[0] is websocket
    assert args[1] is None  # no wakeword engine
    assert args[2] is not None  # detector consumer is initialized
