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
"""Config flow for Oremi Ohunerin wake word integration."""
from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
import websockets
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.config_entries import OptionsFlow
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_LANGUAGE
from .const import CONF_URL
from .const import DEFAULT_LANGUAGE
from .const import DEFAULT_URL
from .const import DOMAIN
from .const import FALLBACK_LANGUAGES
from .const import SUPPORTED_LANGUAGES

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
  """Error to indicate we cannot connect."""


async def async_get_languages(url: str) -> list[str]:
  """Fetch available languages from the Ohunerin server via WebSocket."""
  try:
    async with websockets.connect(url, open_timeout=5) as websocket:
      # The server immediately sends the ServerInitMessage
      msg = await websocket.recv()
      data = json.loads(msg)
      return data.get('available_languages', FALLBACK_LANGUAGES)
  except Exception as err:
    _LOGGER.error('Error fetching languages from Ohunerin server at %s: %s', url, err)
    raise CannotConnect from err


class OhunerinConfigFlow(ConfigFlow, domain=DOMAIN):
  """Handle a config flow for Oremi Ohunerin."""

  VERSION = 1

  def __init__(self) -> None:
    """Initialize the config flow."""
    self._url: str | None = None
    self._languages: list[str] = []

  async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
    """Handle the initial step (URL configuration)."""
    errors = {}
    if user_input is not None:
      url = user_input[CONF_URL].rstrip('/')
      try:
        languages = await async_get_languages(url)
        if not languages:
          languages = FALLBACK_LANGUAGES
        self._url = url
        self._languages = languages
        return await self.async_step_language_settings()
      except CannotConnect:
        errors['base'] = 'cannot_connect'
      except Exception:  # pylint: disable=broad-except
        _LOGGER.exception('Unexpected exception during connection test')
        errors['base'] = 'unknown'

    return self.async_show_form(
      step_id='user',
      data_schema=vol.Schema({
        vol.Required(CONF_URL, default=DEFAULT_URL): str,
      }),
      errors=errors,
    )

  async def async_step_language_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
    """Handle the second step (Language selection)."""
    errors = {}
    if user_input is not None:
      return self.async_create_entry(
        title=f"Oremi Ohunerin ({self._url})",
        data={
          CONF_URL: self._url,
          CONF_LANGUAGE: user_input[CONF_LANGUAGE],
        },
      )

    lang_list = sorted(self._languages) if self._languages else FALLBACK_LANGUAGES
    default_lang = DEFAULT_LANGUAGE if DEFAULT_LANGUAGE in lang_list else lang_list[0]
    lang_options = {lang: SUPPORTED_LANGUAGES.get(lang, lang.upper()) for lang in lang_list}

    return self.async_show_form(
      step_id='language_settings',
      data_schema=vol.Schema({
        vol.Required(CONF_LANGUAGE, default=default_lang): vol.In(lang_options),
      }),
      errors=errors,
    )

  @staticmethod
  @callback
  def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
    """Create the options flow."""
    return OhunerinOptionsFlowHandler(config_entry)


class OhunerinOptionsFlowHandler(OptionsFlow):
  """Handle Options Flow for Oremi Ohunerin."""

  def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
    """Initialize the options flow."""
    self.config_entry = config_entry

  async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
    """Manage the options."""
    if user_input is not None:
      return self.async_create_entry(title='', data=user_input)

    url = self.config_entry.data.get(CONF_URL, DEFAULT_URL)
    try:
      languages = await async_get_languages(url)
    except Exception:
      languages = FALLBACK_LANGUAGES

    lang_list = sorted(languages) if languages else FALLBACK_LANGUAGES
    current_language = self.config_entry.options.get(
      CONF_LANGUAGE, self.config_entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
    )

    if current_language not in lang_list:
      lang_list.append(current_language)
      lang_list.sort()

    lang_options = {lang: SUPPORTED_LANGUAGES.get(lang, lang.upper()) for lang in lang_list}

    return self.async_show_form(
      step_id='init',
      data_schema=vol.Schema({
        vol.Required(CONF_LANGUAGE, default=current_language): vol.In(lang_options),
      }),
    )
