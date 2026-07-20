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
import os

import pytest
import pytest_asyncio

from ohunerin import parse_config_file
from ohunerin.server import Server


@pytest.fixture
def logger():
  return logging.getLogger("test_server_query_params")


@pytest_asyncio.fixture
async def server(logger):
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  config_file = os.path.join(base_dir, "ohunerin", "config.json")
  config = parse_config_file(config_file)
  return Server(config=config, logger=logger)


# ---------------------------------------------------------------------------
# Wakeword detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_query_params_wakeword_only(server):
  path = "/ws?features=wakeword-detection&language=en"
  wk_engine, dt_consumer = server._parse_query_params(path)

  assert wk_engine is not None
  assert dt_consumer is None
  assert wk_engine.is_discriminant("hello hello") is True


@pytest.mark.asyncio
async def test_parse_query_params_wakeword_fr_discriminants(server):
  path = "/ws?features=wakeword-detection&language=fr"
  wk_engine, dt_consumer = server._parse_query_params(path)

  assert wk_engine is not None
  # "remi" is the configured discriminant (accent stripped for pocketsphinx)
  assert wk_engine.is_discriminant("remi") is True
  assert wk_engine.is_discriminant("oremi") is False


@pytest.mark.asyncio
async def test_parse_query_params_missing_language(server):
  path = "/ws?features=wakeword-detection"
  with pytest.raises(ValueError, match="language query parameter is required"):
    server._parse_query_params(path)


@pytest.mark.asyncio
async def test_parse_query_params_unsupported_language(server):
  path = "/ws?features=wakeword-detection&language=de"
  with pytest.raises(ValueError, match="Unsupported language: de"):
    server._parse_query_params(path)


# ---------------------------------------------------------------------------
# Sound detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_query_params_sound_only_no_filter(server):
  """No sounds param → uses the full server-side sound list."""
  path = "/ws?features=sound-detection"
  wk_engine, dt_consumer = server._parse_query_params(path)

  assert wk_engine is None
  assert dt_consumer is not None
  assert dt_consumer._detector.classifier is not None


@pytest.mark.asyncio
async def test_parse_query_params_sound_csv_filter(server):
  """sounds param (CSV) is intersected with the server's configured list."""
  path = "/ws?features=sound-detection&sounds=Shout,Laughter"
  wk_engine, dt_consumer = server._parse_query_params(path)

  assert wk_engine is None
  assert dt_consumer is not None


@pytest.mark.asyncio
async def test_parse_query_params_sound_json_filter(server):
  """sounds param (JSON array) is intersected with the server's configured list."""
  path = '/ws?features=sound-detection&sounds=["Shout","Laughter"]'
  wk_engine, dt_consumer = server._parse_query_params(path)

  assert wk_engine is None
  assert dt_consumer is not None


@pytest.mark.asyncio
async def test_parse_query_params_sound_filter_ignores_unknown(server):
  """Sounds not in the server config are silently dropped from the allowlist."""
  # "Dog" and "Cat" are not in config.json sounds → filtered out; only "Shout" passes
  path = "/ws?features=sound-detection&sounds=Shout,Dog,Cat"
  _, dt_consumer = server._parse_query_params(path)

  # Consumer should still be created (Shout is a valid server sound)
  assert dt_consumer is not None


# ---------------------------------------------------------------------------
# Combined features
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_query_params_both_features(server):
  path = "/ws?features=wakeword-detection,sound-detection&language=fr"
  wk_engine, dt_consumer = server._parse_query_params(path)

  assert wk_engine is not None
  assert dt_consumer is not None


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_query_params_no_features_raises_error(server):
  path = "/ws?language=fr"
  with pytest.raises(ValueError, match="features query parameter is required"):
    server._parse_query_params(path)
