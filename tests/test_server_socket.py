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
import socket
from pathlib import Path

import aiohttp
import pytest
import pytest_asyncio
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed
from websockets.exceptions import InvalidStatus

from ohunerin.models.sound import SoundsConfig
from ohunerin.models.wakeword import WakewordsConfig
from ohunerin.server import Server
from ohunerin.server.websocket import ServerEventType

# These tests load the real yamnet.tflite model and open real sockets; run
# ./scripts/install-model.sh first, exactly like the rest of the suite. They
# cover the websockets.asyncio.server integration end to end: HTTP routes,
# WebSocket upgrade, close codes and clean-disconnect reporting.

BASE_DIR = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
WINDOW_BYTES = 15600


@pytest.fixture
def logger():
  return logging.getLogger("test_server_socket")


def find_free_port() -> int:
  with socket.socket() as sock:
    sock.bind((HOST, 0))
    return sock.getsockname()[1]


@pytest_asyncio.fixture
async def running_server(logger):
  """A real Server listening on an ephemeral port, torn down with the test."""
  with open(BASE_DIR / "config.json", encoding="utf-8") as file:
    raw = json.load(file)

  server = Server(
    wakewords_config=WakewordsConfig.model_validate(raw.get("wakewords", [])),
    sounds_config=SoundsConfig.model_validate(raw.get("sounds", {})),
    threshold=0.65,
    model=BASE_DIR / "models" / "yamnet.tflite",
  )

  port = find_free_port()
  task = asyncio.create_task(server.listen(HOST, port))

  # Wait until the listening socket accepts connections.
  for _ in range(300):
    if task.done():
      await task
      raise RuntimeError("server stopped before accepting connections")

    try:
      _reader, writer = await asyncio.open_connection(HOST, port)
    except OSError:
      await asyncio.sleep(0.01)
    else:
      writer.close()
      await writer.wait_closed()
      break
  else:
    raise RuntimeError("server did not start listening")

  try:
    yield server, port
  finally:
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_http_routes_over_a_real_socket(running_server):
  _server, port = running_server
  base_url = f"http://{HOST}:{port}"

  async with aiohttp.ClientSession() as session:
    async with session.get(f"{base_url}/health") as response:
      assert response.status == 200
      assert response.headers["Access-Control-Allow-Origin"] == "*"
      assert (await response.json())["name"] == "oremi-ohunerin"

    async with session.get(f"{base_url}/", allow_redirects=False) as response:
      assert response.status == 302
      assert response.headers["Location"] == "/health"

    async with session.get(f"{base_url}/api/sounds") as response:
      assert response.status == 200
      assert "Speech" in await response.json()

    async with session.get(f"{base_url}/invalid") as response:
      assert response.status == 404
      assert await response.text() == "Not Found"


@pytest.mark.asyncio
async def test_non_websocket_path_is_rejected_before_upgrade(running_server):
  _server, port = running_server

  with pytest.raises(InvalidStatus) as excinfo:
    async with connect(f"ws://{HOST}:{port}/not-ws"):
      pass

  assert excinfo.value.response.status_code == 404


@pytest.mark.asyncio
async def test_missing_features_closes_with_1003(running_server):
  _server, port = running_server

  async with connect(f"ws://{HOST}:{port}/ws") as websocket:
    with pytest.raises(ConnectionClosed) as excinfo:
      await websocket.recv()

  assert excinfo.value.rcvd.code == 1003


@pytest.mark.asyncio
async def test_unsupported_language_closes_with_1003(running_server):
  _server, port = running_server

  async with connect(f"ws://{HOST}:{port}/ws?features=wakeword-detection&language=xx") as websocket:
    with pytest.raises(ConnectionClosed) as excinfo:
      await websocket.recv()

  assert excinfo.value.rcvd.code == 1003


@pytest.mark.asyncio
async def test_sound_session_streams_and_reports_a_clean_close(running_server):
  server, port = running_server
  closes: list[tuple[int | None, object]] = []

  async def on_close(websocket, exception):
    closes.append((websocket.close_code, exception))

  server.event_manager.on(ServerEventType.CONNECTION_CLOSE, on_close)

  async with connect(f"ws://{HOST}:{port}/ws?features=sound-detection") as websocket:
    await websocket.send(b"\x00" * WINDOW_BYTES)
    await asyncio.sleep(0.05)

  for _ in range(300):
    if closes:
      break
    await asyncio.sleep(0.01)

  # A normal closure ends the message iterator instead of raising
  # ConnectionClosedOK, so the close must be reported from the connection state.
  assert len(closes) == 1
  assert closes[0][0] == 1000
  assert closes[0][1] is None
