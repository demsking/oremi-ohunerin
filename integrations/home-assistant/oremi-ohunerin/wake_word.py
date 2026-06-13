# Copyright 2024-2026 Sébastien Demanou. All Rights Reserved.
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
"""Support for the Oremi Ohunerin wake word service."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterable

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
import websockets
from homeassistant.components import wake_word
from homeassistant.components.wake_word import DetectionResult
from homeassistant.components.wake_word import WakeWord
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.typing import DiscoveryInfoType

from . import OhunerinConfigEntry
from .const import CONF_LANGUAGE
from .const import CONF_URL
from .const import DEFAULT_LANGUAGE
from .const import DEFAULT_URL
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Extend the base wake_word platform schema to allow YAML configuration
PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
  {
    vol.Required(CONF_URL, default=DEFAULT_URL): cv.string,
    vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): cv.string,
  }
)


async def async_get_engine(
  hass: HomeAssistant,
  config: ConfigType,
  discovery_info: DiscoveryInfoType | None = None,
) -> wake_word.Provider | None:
  """Set up the Oremi Ohunerin wake word platform from configuration.yaml."""
  # Import configuration into Config Flow
  hass.async_create_task(
    hass.config_entries.flow.async_init(
      DOMAIN, context={'source': SOURCE_IMPORT}, data=config
    )
  )
  return None


async def async_setup_entry(
  hass: HomeAssistant,
  config_entry: OhunerinConfigEntry,
  async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up the Oremi Ohunerin wake word platform from a config entry."""
  url = config_entry.runtime_data.url
  language = config_entry.runtime_data.language

  async_add_entities(
    [OhunerinWakeWordEntity(url, language, entry_id=config_entry.entry_id)]
  )


class OhunerinWakeWordEntity(wake_word.WakeWordDetectionEntity):
  """Representation of the Oremi Ohunerin wake word entity."""

  def __init__(self, url: str, language: str, *, entry_id: str) -> None:
    """Initialize the Oremi Ohunerin wake word entity."""
    self._url = url
    self._language = language
    self._attr_name = 'Oremi Ohunerin'
    self._attr_unique_id = f'{entry_id}-wakeword'

  async def get_supported_wake_words(self) -> list[WakeWord]:
    """Return a list of supported wake words."""
    return [
      WakeWord(id='oremi', name='Oremi', phrase='oremi'),
      WakeWord(id='dikomlam', name='Dikomlam', phrase='dikomlam'),
    ]

  async def _async_process_audio_stream(
    self,
    stream: AsyncIterable[tuple[bytes, int]],
    wake_word_id: str | None,
  ) -> DetectionResult | None:
    """Try to detect wake word(s) in an audio stream."""
    url = self._url
    language = self._language

    # Build WebSocket URL
    base_url = url.rstrip('/')
    if base_url.endswith('/ws'):
      ws_url = f'{base_url}?language={language}&features=wakeword-detection'
    else:
      ws_url = f'{base_url}/ws?language={language}&features=wakeword-detection'

    try:
      async with websockets.connect(ws_url, open_timeout=5) as websocket:
        # Stream audio chunks and monitor detection response concurrently
        result_queue = asyncio.Queue()

        async def read_responses():
          try:
            async for message in websocket:
              data = json.loads(message)
              if data.get('type') == 'sound' and data.get('sound') in ['oremi', 'dikomlam', 'wakeword']:
                word = data.get('sound')
                _LOGGER.debug('Wake word detected by Ohunerin: %s', word)
                await result_queue.put(('detection', word))
                return
            # Connection closed normally
            await result_queue.put(('closed', None))
          except asyncio.CancelledError:
            pass
          except Exception as err:
            _LOGGER.error('Error reading from Ohunerin WebSocket: %s', err)
            await result_queue.put(('error', err))

        # Start response listener task
        read_task = asyncio.create_task(read_responses())

        try:
          # Stream the audio chunks to the server
          async for chunk, timestamp in stream:
            # Check for early detection/error/closure
            if not result_queue.empty():
              status, val = result_queue.get_nowait()
              if status == 'detection':
                return DetectionResult(ww_id=val, timestamp=timestamp)
              elif status == 'error':
                raise val
              elif status == 'closed':
                _LOGGER.warning('Ohunerin WebSocket connection closed prematurely')
                break

            # Send the audio chunk to the server
            await websocket.send(chunk)

            # Yield control to allow reader to run
            await asyncio.sleep(0)

          # Wait briefly for any late detection response after sending all chunks
          try:
            await asyncio.wait_for(read_task, timeout=0.1)
          except asyncio.TimeoutError:
            pass

          if not result_queue.empty():
            status, val = result_queue.get_nowait()
            if status == 'detection':
              return DetectionResult(ww_id=val, timestamp=timestamp)

        finally:
          read_task.cancel()
          try:
            await read_task
          except Exception:
            pass

    except Exception as err:
      _LOGGER.error('Error communicating with Oremi Ohunerin server: %s', err)
      return None
