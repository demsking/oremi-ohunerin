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
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from ohunerin.core.settings import Settings

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config.json"
MODEL_PATH = BASE_DIR / "models" / "yamnet.tflite"


def test_settings_defaults():
  settings = Settings(
    config_path=CONFIG_PATH,
    model_path=MODEL_PATH,
  )
  assert settings.server_host == "127.0.0.1"
  assert settings.server_port == 5023
  assert settings.log_level == "INFO"
  assert settings.threshold == 0.1
  assert settings.wakewords_config is not None
  assert settings.sounds_config is not None


def test_settings_env_prefix():
  env = {
    "OREMI_OHUNERIN_SERVER_HOST": "0.0.0.0",
    "OREMI_OHUNERIN_SERVER_PORT": "9090",
    "OREMI_OHUNERIN_LOG_LEVEL": "DEBUG",
    "OREMI_OHUNERIN_THRESHOLD": "0.85",
    "OREMI_OHUNERIN_CONFIG_PATH": str(CONFIG_PATH),
    "OREMI_OHUNERIN_MODEL_PATH": str(MODEL_PATH),
  }
  with patch.dict(os.environ, env):
    settings = Settings()
    assert settings.server_host == "0.0.0.0"
    assert settings.server_port == 9090
    assert settings.log_level == "DEBUG"
    assert settings.threshold == 0.85
    assert settings.config_path == CONFIG_PATH


def test_settings_partial_override_sounds_missing():
  with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tmp:
    json.dump({"sounds": {"allowlist": ["Speech"]}}, tmp)
    tmp_path = Path(tmp.name)

  try:
    settings = Settings(config_path=tmp_path, model_path=MODEL_PATH)
    assert settings.sounds_config.allowlist == ["Speech"]
    # wakewords should fall back to default wakewords
    assert len(settings.wakewords_config.wakewords) > 0
  finally:
    os.unlink(tmp_path)


def test_settings_partial_override_wakewords_missing():
  custom_wakewords = [
    {
      "language": "en",
      "word": "computer",
      "phones": ["K AH M P Y UW T ER"],
    }
  ]
  with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tmp:
    json.dump({"wakewords": custom_wakewords}, tmp)
    tmp_path = Path(tmp.name)

  try:
    settings = Settings(config_path=tmp_path, model_path=MODEL_PATH)
    assert len(settings.wakewords_config.wakewords) == 1
    assert settings.wakewords_config.wakewords[0].word == "computer"
    # sounds should fall back to default sounds
    assert settings.sounds_config.allowlist == []
  finally:
    os.unlink(tmp_path)
