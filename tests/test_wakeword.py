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

from ohunerin.models import DictionaryEntry
from ohunerin.models import OhunerinConfig
from ohunerin.models import WakewordSetting
from ohunerin.wakeword import WakewordEngine


@pytest.fixture
def logger():
  return logging.getLogger("test_wakeword")


@pytest.fixture
def config_data() -> dict[str, WakewordSetting]:
  """Parse config.json into a language-keyed dict of WakewordSetting objects."""
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  config_file = os.path.join(base_dir, "ohunerin", "config.json")
  config_dir = os.path.dirname(os.path.abspath(config_file))

  language_model_paths: dict[str, tuple[str, str]] = {
    'fr': (
      'models/wakeword-fr/cmusphinx-fr-ptm-8khz-5.2',
      'models/wakeword-fr/pronounciation-dictionary.dict',
    ),
    'en': (
      'models/wakeword-en/acoustic-model',
      'models/wakeword-en/pronounciation-dictionary.dict',
    ),
  }

  with open(config_file, encoding="utf-8") as f:
    raw = json.load(f)

  ohunerin_config = OhunerinConfig.model_validate(raw)

  language_wakewords: dict[str, list[DictionaryEntry]] = {}
  language_discriminants: dict[str, list[DictionaryEntry]] = {}

  for entry in ohunerin_config.wakewords:
    lang = entry.language
    language_wakewords.setdefault(lang, []).append(
      DictionaryEntry(word=entry.word, phones=entry.phones)
    )
    for disc in entry.discriminants:
      language_discriminants.setdefault(lang, []).append(disc)

  settings: dict[str, WakewordSetting] = {}
  for language, wakewords in language_wakewords.items():
    model_rel, dict_rel = language_model_paths.get(
      language,
      (f'models/wakeword-{language}/acoustic-model', f'models/wakeword-{language}/pronounciation-dictionary.dict'),
    )
    settings[language] = WakewordSetting(
      model=os.path.abspath(os.path.join(config_dir, model_rel)),
      dictionary=os.path.abspath(os.path.join(config_dir, dict_rel)),
      wakewords=wakewords,
      discriminants=language_discriminants.get(language, []),
    )

  return settings


def test_wakeword_engine_is_discriminant_fr(config_data, logger):
  engine = WakewordEngine(config_data["fr"], logger)

  # "remi" is a predefined discriminant in the French config (stored without accent)
  assert engine.is_discriminant("remi") is True

  # "oremi" is the wakeword, not a discriminant
  assert engine.is_discriminant("oremi") is False

  # Repeated-word phrases are always discriminants
  assert engine.is_discriminant("test test") is True
  assert engine.is_discriminant("test hello") is False


def test_wakeword_engine_is_discriminant_en(config_data, logger):
  engine = WakewordEngine(config_data["en"], logger)

  # English config has no explicit discriminants
  assert engine.is_discriminant("rémi") is False
  assert engine.is_discriminant("oremi") is False
  assert engine.is_discriminant("hello hello") is True
  assert engine.is_discriminant("hello world") is False


def test_wakeword_engine_process_raw_dummy(config_data, logger):
  engine = WakewordEngine(config_data["en"], logger)

  engine.start_utt()

  # Send 1 second of silent mono audio (16000 Hz, 16-bit PCM → 32000 bytes)
  dummy_chunk = b"\x00" * 32000
  sound, score = engine.process_raw(dummy_chunk)

  # Silent/dummy input should not trigger any wakeword
  assert sound is None
  assert score == 0.0

  engine.end_utt()
