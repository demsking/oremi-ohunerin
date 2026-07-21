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
import logging
import ssl
import traceback
from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
from collections.abc import Coroutine
from enum import StrEnum

import websockets.legacy.server as Websockets
from websockets.exceptions import ConnectionClosedError
from websockets.exceptions import ConnectionClosedOK

from ohunerin.core.events import EventManager

logger = logging.getLogger(__name__)

WebSocketConnection = Websockets.WebSocketServerProtocol
Data = bytes | str


class ServerEventType(StrEnum):
  NEW_CONNECTION = "new_connection"
  CONNECTION_CLOSE = "connection_close"


class WebSocketServer(ABC):
  """Abstract base class for asynchronous WebSocket servers."""

  def __init__(
    self,
    *,
    server_header: str,
    cert_file: str | None = None,
    key_file: str | None = None,
    password: str | None = None,
    on_listening: Callable[[], Coroutine] | None = None,
    on_shutdown: Callable[[], Coroutine] | None = None,
    **kwargs,
  ) -> None:
    self.verbose: bool = logger.level == logging.DEBUG
    self.kwargs = kwargs
    self.server_header: str = server_header
    self.on_listening = on_listening
    self.on_shutdown = on_shutdown
    self.ssl_context = self._create_ssl_context(cert_file=cert_file, key_file=key_file, password=password)
    self.event_manager = EventManager[ServerEventType, WebSocketServer]()

  def _create_ssl_context(
    self,
    *,
    cert_file: str | None = None,
    key_file: str | None = None,
    password: str | None = None,
  ) -> ssl.SSLContext | None:
    ssl_context = None

    if cert_file:
      ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
      logger.info(f'Using certificate file "{cert_file}"')

      if key_file:
        logger.info(f'Using key file "{key_file}"')

      ssl_context.load_cert_chain(cert_file, key_file, password)
    return ssl_context

  async def _handle_connection_close(
    self,
    websocket: WebSocketConnection,
    exception: ConnectionClosedOK | ConnectionClosedError,
  ) -> None:
    if exception.reason:
      logger.info(f"Connection closed {websocket.remote_address} with code {exception.code}. Reason: {exception.reason}")
    else:
      logger.info(f"Connection closed {websocket.remote_address} with code {exception.code}")

    await self.event_manager.trigger(ServerEventType.CONNECTION_CLOSE, (websocket, exception))

  @abstractmethod
  async def _process_request(self, websocket: WebSocketConnection, message: Data) -> None:
    """Process incoming WebSocket frame/message."""

  async def _handle_messages(self, websocket: WebSocketConnection) -> None:
    async for message in websocket:
      task = asyncio.create_task(
        self._process_request(websocket, message),
        name="Processing Request Task",
      )
      task.add_done_callback(self._handle_processing_done_task)

  def _handle_processing_done_task(self, task: asyncio.Task) -> None:
    try:
      task.result()
    except Exception as exception:
      logger.error(f"Error in task {task.get_name()}: {exception}")
      if self.verbose:
        traceback.print_exc()

  async def _handle_new_connection(self, websocket: WebSocketConnection) -> None:
    user_agent = websocket.request_headers.get("User-Agent", "unknown") if hasattr(websocket, "request_headers") else ""
    logger.info(f"Connection from {websocket.remote_address} {user_agent}")

    try:
      await self._handle_messages(websocket)
    except (ValueError, TypeError) as exception:
      error_message = f"Invalid Message: {exception}"
      await websocket.close(code=1003, reason=error_message)
      logger.error(error_message)
      if self.verbose:
        traceback.print_exc()
    except ConnectionClosedOK as exception:
      await self._handle_connection_close(websocket, exception)

  async def _handler_client(self, websocket: WebSocketConnection) -> None:
    try:
      await self.event_manager.trigger(ServerEventType.NEW_CONNECTION, websocket)
      await self._handle_new_connection(websocket)
    except (ConnectionClosedOK, ConnectionClosedError) as exception:
      await self._handle_connection_close(websocket, exception)
    except Exception as error:
      error_message = f"Unexpected Error: {error}"
      logger.error(error_message)
      await websocket.close(code=4000, reason=error_message)
      if self.verbose:
        traceback.print_exc()

  async def listen(
    self,
    host: str,
    port: int,
    open_timeout: float | None = 10,
    ping_interval: float | None = 20,
    ping_timeout: float | None = 20,
    close_timeout: float | None = None,
  ) -> None:
    """Listens for incoming WebSocket connections."""
    async with Websockets.serve(
      self._handler_client,
      host,
      port,
      ssl=self.ssl_context,
      server_header=self.server_header,
      open_timeout=open_timeout,
      ping_interval=ping_interval,
      ping_timeout=ping_timeout,
      close_timeout=close_timeout,
      **self.kwargs,
    ):
      if self.on_listening:
        await self.on_listening()

      try:
        await asyncio.Future()
      except asyncio.exceptions.CancelledError:
        pass
      finally:
        if self.on_shutdown:
          await self.on_shutdown()


class BroadcastingWebSocketServer(WebSocketServer):
  """WebSocket server with broadcasting capabilities to active connected clients."""

  def __init__(
    self,
    *,
    server_header: str,
    cert_file: str | None = None,
    key_file: str | None = None,
    password: str | None = None,
    on_listening: Callable[[], Coroutine] | None = None,
    on_shutdown: Callable[[], Coroutine] | None = None,
    **kwargs,
  ) -> None:
    super().__init__(
      server_header=server_header,
      cert_file=cert_file,
      key_file=key_file,
      password=password,
      on_listening=on_listening,
      on_shutdown=on_shutdown,
      **kwargs,
    )
    self._clients: list[WebSocketConnection] = []

  async def _handle_new_connection(self, websocket: WebSocketConnection) -> None:
    self._clients.append(websocket)
    await super()._handle_new_connection(websocket)

  async def _handle_connection_close(
    self,
    websocket: WebSocketConnection,
    exception: ConnectionClosedOK | ConnectionClosedError,
  ) -> None:
    if websocket in self._clients:
      self._clients.remove(websocket)
    await super()._handle_connection_close(websocket, exception)

  async def broadcast(self, message: Data) -> None:
    """Broadcast message to all connected clients."""
    for client in self._clients:
      if not client.closed:
        try:
          await client.send(message)
        except Exception as exception:
          client_id = getattr(client, "id", str(client.remote_address))
          logger.error(f"Unexpected error occurred when broadcasting to {client_id}: {exception}")
