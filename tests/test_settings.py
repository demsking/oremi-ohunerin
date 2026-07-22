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
import os
from pathlib import Path
from unittest.mock import patch

from ohunerin.core.settings import Settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAKEWORDS_CONFIG_PATH = os.path.join(BASE_DIR, "data", "wakewords", "wakeword.json")
SOUNDS_CONFIG_PATH = os.path.join(BASE_DIR, "data", "sounds", "sounds.json")
MODEL_PATH = os.path.join(BASE_DIR, "models", "yamnet.tflite")


def test_settings_defaults():
  settings = Settings(
    wakeword_config_path=WAKEWORDS_CONFIG_PATH,
    sounds_config_path=SOUNDS_CONFIG_PATH,
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
    "OREMI_OHUNERIN_WAKEWORD_CONFIG_PATH": WAKEWORDS_CONFIG_PATH,
    "OREMI_OHUNERIN_SOUNDS_CONFIG_PATH": SOUNDS_CONFIG_PATH,
    "OREMI_OHUNERIN_MODEL_PATH": MODEL_PATH,
  }
  with patch.dict(os.environ, env):
    settings = Settings()
    assert settings.server_host == "0.0.0.0"
    assert settings.server_port == 9090
    assert settings.log_level == "DEBUG"
    assert settings.threshold == 0.85
    assert settings.wakeword_config_path == Path(WAKEWORDS_CONFIG_PATH)
    assert settings.sounds_config_path == Path(SOUNDS_CONFIG_PATH)
