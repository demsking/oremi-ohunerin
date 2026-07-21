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
import pytest

from ohunerin.core.events import EventManager


@pytest.mark.asyncio
async def test_event_manager_on_trigger():
  manager = EventManager[str, None]()
  called = []

  async def handler(data):
    called.append(data)

  manager.on("test_event", handler)
  await manager.trigger("test_event", "hello")

  assert called == ["hello"]


@pytest.mark.asyncio
async def test_event_manager_off():
  manager = EventManager[str, None]()
  called = []

  async def handler(data):
    called.append(data)

  manager.on("test_event", handler)
  manager.off("test_event", handler)
  await manager.trigger("test_event", "hello")

  assert called == []
