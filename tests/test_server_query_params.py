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
import http
import json
import logging
import os
import pytest
from ohunerin.server import Server


@pytest.fixture
def logger():
  return logging.getLogger("test_server_query_params")


@pytest.fixture
def config_file():
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  return os.path.join(base_dir, "ohunerin", "config.json")


@pytest.mark.asyncio
async def test_parse_query_params_wakeword_only(config_file, logger):
  server = Server(config_file=config_file, threshold=0.1, logger=logger)

  # Check standard wakeword-detection feature
  path = "/ws?features=wakeword-detection&language=en"
  wk_engine, dt_consumer = server._parse_query_params(path)
  
  assert wk_engine is not None
  assert dt_consumer is None
  
  # Check is_discriminant on the generated engine
  assert wk_engine.is_discriminant("hello hello") is True


@pytest.mark.asyncio
async def test_parse_query_params_sound_only(config_file, logger):
  server = Server(config_file=config_file, threshold=0.1, logger=logger)

  # Check sound-detection feature with csv allowlist
  path = "/ws?features=sound-detection&allowlist=Dog,Cat"
  wk_engine, dt_consumer = server._parse_query_params(path)
  
  assert wk_engine is None
  assert dt_consumer is not None
  assert dt_consumer._detector.classifier is not None


@pytest.mark.asyncio
async def test_parse_query_params_sound_only_json_allowlist(config_file, logger):
  server = Server(config_file=config_file, threshold=0.1, logger=logger)

  # Check sound-detection feature with JSON allowlist
  path = '/ws?features=sound-detection&allowlist=["Dog","Cat"]'
  wk_engine, dt_consumer = server._parse_query_params(path)
  
  assert wk_engine is None
  assert dt_consumer is not None


@pytest.mark.asyncio
async def test_parse_query_params_both_features(config_file, logger):
  server = Server(config_file=config_file, threshold=0.1, logger=logger)

  # Check both features
  path = "/ws?features=wakeword-detection,sound-detection&language=fr"
  wk_engine, dt_consumer = server._parse_query_params(path)
  
  assert wk_engine is not None
  assert dt_consumer is not None
  assert wk_engine.is_discriminant("rémi") is True


@pytest.mark.asyncio
async def test_parse_query_params_missing_language(config_file, logger):
  server = Server(config_file=config_file, threshold=0.1, logger=logger)

  path = "/ws?features=wakeword-detection"
  with pytest.raises(ValueError, match="language query parameter is required"):
    server._parse_query_params(path)


@pytest.mark.asyncio
async def test_parse_query_params_unsupported_language(config_file, logger):
  server = Server(config_file=config_file, threshold=0.1, logger=logger)

  path = "/ws?features=wakeword-detection&language=de"
  with pytest.raises(ValueError, match="Unsupported language: de"):
    server._parse_query_params(path)


@pytest.mark.asyncio
async def test_parse_query_params_custom_wakewords(config_file, logger):
  server = Server(config_file=config_file, threshold=0.1, logger=logger)

  # Valid custom wakeword and discriminant entries JSON string
  wakewords_json = json.dumps([{"word": "computer", "phones": ["K AH M P Y UW T ER"]}])
  discriminants_json = json.dumps([{"word": "commuter", "phones": ["K AH M Y UW T ER"]}])
  path = f"/ws?features=wakeword-detection&language=en&wakewords={wakewords_json}&discriminants={discriminants_json}"
  
  wk_engine, dt_consumer = server._parse_query_params(path)
  assert wk_engine is not None
  # Ensure the custom discriminant was added and is correctly matched
  assert wk_engine.is_discriminant("commuter") is True
  assert wk_engine.is_discriminant("computer") is False


@pytest.mark.asyncio
async def test_parse_query_params_invalid_wakewords_json(config_file, logger):
  server = Server(config_file=config_file, threshold=0.1, logger=logger)

  path = "/ws?features=wakeword-detection&language=en&wakewords=invalid"
  with pytest.raises(ValueError, match="Invalid wakewords"):
    server._parse_query_params(path)


@pytest.mark.asyncio
async def test_parse_query_params_invalid_discriminants_json(config_file, logger):
  server = Server(config_file=config_file, threshold=0.1, logger=logger)

  path = "/ws?features=wakeword-detection&language=en&discriminants=invalid"
  with pytest.raises(ValueError, match="Invalid discriminants"):
    server._parse_query_params(path)
