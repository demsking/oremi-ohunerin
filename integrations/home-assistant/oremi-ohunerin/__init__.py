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
"""The Oremi Ohunerin wake word integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_LANGUAGE
from .const import CONF_URL

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.WAKE_WORD]


@dataclass
class OhunerinRuntimeData:
  """Runtime data stored in ConfigEntry."""

  url: str
  language: str


# ConfigEntry type alias
OhunerinConfigEntry = ConfigEntry[OhunerinRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: OhunerinConfigEntry) -> bool:
  """Set up Oremi Ohunerin wake word from a config entry."""
  # Get config values
  url = entry.data[CONF_URL]
  language = entry.options.get(CONF_LANGUAGE, entry.data.get(CONF_LANGUAGE, 'fr'))

  # Store runtime data directly on entry
  entry.runtime_data = OhunerinRuntimeData(
    url=url,
    language=language,
  )

  # Register listener to handle option updates
  entry.async_on_unload(entry.add_update_listener(async_update_options))

  await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
  return True


async def async_unload_entry(hass: HomeAssistant, entry: OhunerinConfigEntry) -> bool:
  """Unload a config entry."""
  return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: OhunerinConfigEntry) -> None:
  """Handle options update."""
  # Reload the platforms to apply option changes
  await hass.config_entries.async_reload(entry.entry_id)
