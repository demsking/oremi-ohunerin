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
from collections.abc import Callable
from collections.abc import Coroutine
from typing import Any
from typing import Generic
from typing import Hashable
from typing import TypeVar

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=Hashable)
S = TypeVar("S")

EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventManager(Generic[E, S]):
  """Type-safe async event manager for registering and triggering event handlers."""

  def __init__(self) -> None:
    self._listeners: dict[E, list[EventHandler]] = {}

  def on(self, event: E, handler: EventHandler) -> None:
    """Register an asynchronous event handler for a specific event type."""
    if event not in self._listeners:
      self._listeners[event] = []
    self._listeners[event].append(handler)

  def off(self, event: E, handler: EventHandler) -> None:
    """Unregister an asynchronous event handler for a specific event type."""
    if event in self._listeners and handler in self._listeners[event]:
      self._listeners[event].remove(handler)

  async def trigger(self, event: E, data: Any = None) -> None:
    """Trigger all event handlers registered for the given event type."""
    handlers = self._listeners.get(event, [])
    for handler in handlers:
      try:
        if data is not None:
          if isinstance(data, tuple):
            await handler(*data)
          else:
            await handler(data)
        else:
          await handler()
      except Exception as exc:
        logger.error(f"Error executing handler for event '{event}': {exc}")
