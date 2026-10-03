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
import logging
import uuid

import pytest
from websockets.protocol import State

from ohunerin.server.websocket import BroadcastingWebSocketServer


@pytest.fixture
def logger():
  return logging.getLogger("test_websocket_broadcast")


class ConcreteServer(BroadcastingWebSocketServer):
  """Concrete BroadcastingWebSocketServer: the base class is abstract."""

  async def _process_request(self, websocket, message):
    pass


class FakeConnection:
  """Minimal stand-in for websockets.asyncio.server.ServerConnection."""

  def __init__(self, state=State.OPEN):
    self.state = state
    self.id = uuid.uuid4()
    self.remote_address = ("127.0.0.1", 0)
    self.close_code = None
    self.close_reason = None
    self.sent = []
    self.fail = False

  async def send(self, message):
    if self.fail:
      raise RuntimeError("send failed")
    self.sent.append(message)


@pytest.mark.asyncio
async def test_broadcast_reaches_open_connections_only(logger):
  server = ConcreteServer(server_header="oremi-ohunerin/test")
  opened = FakeConnection(State.OPEN)
  closing = FakeConnection(State.CLOSING)
  closed = FakeConnection(State.CLOSED)
  server._clients.extend([opened, closing, closed])  # type: ignore[attr-defined]

  await server.broadcast("payload")

  assert opened.sent == ["payload"]
  assert closing.sent == []
  assert closed.sent == []


@pytest.mark.asyncio
async def test_broadcast_keeps_going_when_one_send_fails(logger):
  server = ConcreteServer(server_header="oremi-ohunerin/test")
  broken = FakeConnection(State.OPEN)
  broken.fail = True
  healthy = FakeConnection(State.OPEN)
  server._clients.extend([broken, healthy])  # type: ignore[attr-defined]

  await server.broadcast("payload")

  assert healthy.sent == ["payload"]


@pytest.mark.asyncio
async def test_connection_close_removes_the_client(logger):
  server = ConcreteServer(server_header="oremi-ohunerin/test")
  connection = FakeConnection(State.CLOSED)
  server._clients.append(connection)  # type: ignore[attr-defined]

  await server._handle_connection_close(connection)

  assert connection not in server._clients  # type: ignore[attr-defined]
