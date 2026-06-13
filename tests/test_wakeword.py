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
import json
import logging
import os
import pytest
from ohunerin.wakeword import WakewordEngine, WakewordSetting


@pytest.fixture
def logger():
  return logging.getLogger("test_wakeword")


@pytest.fixture
def config_data():
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  config_file = os.path.join(base_dir, "ohunerin", "config.json")
  config_dir = os.path.dirname(config_file)
  
  with open(config_file, encoding="utf-8") as f:
    data = json.load(f)
    
  # Resolve paths relative to config file location
  for lang, locale_config in data.items():
    for key in ("model", "dictionary"):
      if key in locale_config and not os.path.isabs(locale_config[key]):
        locale_config[key] = os.path.abspath(os.path.join(config_dir, locale_config[key]))
        
  return data


def test_wakeword_engine_is_discriminant_fr(config_data, logger):
  fr_setting = WakewordSetting.model_validate(config_data["fr"])
  engine = WakewordEngine(fr_setting, logger)
  
  # "rémi" is a predefined discriminant in French config
  assert engine.is_discriminant("rémi") is True
  
  # "oremi" is the wakeword, should not be discriminant
  assert engine.is_discriminant("oremi") is False
  
  # Word with space containing identical parts should be discriminant
  assert engine.is_discriminant("test test") is True
  assert engine.is_discriminant("test hello") is False


def test_wakeword_engine_is_discriminant_en(config_data, logger):
  en_setting = WakewordSetting.model_validate(config_data["en"])
  engine = WakewordEngine(en_setting, logger)
  
  # English config has no discriminants by default
  assert engine.is_discriminant("rémi") is False
  assert engine.is_discriminant("oremi") is False
  assert engine.is_discriminant("hello hello") is True
  assert engine.is_discriminant("hello world") is False


def test_wakeword_engine_process_raw_dummy(config_data, logger):
  en_setting = WakewordSetting.model_validate(config_data["en"])
  engine = WakewordEngine(en_setting, logger)
  
  engine.start_utt()
  
  # Send 1 second of silent mono audio (16000Hz, 16-bit PCM -> 32000 bytes)
  dummy_chunk = b"\x00" * 32000
  sound, score = engine.process_raw(dummy_chunk)
  
  # Silent/dummy input should not trigger any wakeword
  assert sound is None
  assert score == 0.0
  
  engine.end_utt()
