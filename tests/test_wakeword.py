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

from ohunerin.engines.wakeword import WakewordEngine
from ohunerin.models.wakeword import DictionaryEntry
from ohunerin.models.wakeword import WakewordsConfig
from ohunerin.models.wakeword import WakewordSetting


@pytest.fixture
def logger():
  return logging.getLogger("test_wakeword")


@pytest.fixture
def config_data() -> dict[str, WakewordSetting]:
  """Parse wakeword.json into a language-keyed dict of WakewordSetting objects."""
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  wakewords_file = os.path.join(base_dir, "data", "wakeword.json")

  language_data_paths: dict[str, tuple[str, str]] = {
    "fr": (
      "models/wakeword-fr/cmusphinx-fr-ptm-8khz-5.2",
      "models/wakeword-fr/pronounciation-dictionary.dict",
    ),
    "en": (
      "models/wakeword-en/acoustic-model",
      "models/wakeword-en/pronounciation-dictionary.dict",
    ),
  }

  with open(wakewords_file, encoding="utf-8") as f:
    wakewords_config = WakewordsConfig.model_validate_json(f.read())

  language_wakewords: dict[str, list[DictionaryEntry]] = {}
  language_discriminants: dict[str, list[DictionaryEntry]] = {}

  for entry in wakewords_config.wakewords:
    lang = entry.language
    language_wakewords.setdefault(lang, []).append(DictionaryEntry(word=entry.word, phones=entry.phones))
    for disc in entry.discriminants:
      language_discriminants.setdefault(lang, []).append(disc)

  settings: dict[str, WakewordSetting] = {}
  for language, wakewords in language_wakewords.items():
    model_rel, dict_rel = language_data_paths.get(
      language,
      (f"models/wakeword-{language}/acoustic-model", f"models/wakeword-{language}/pronounciation-dictionary.dict"),
    )
    settings[language] = WakewordSetting(
      model=os.path.abspath(os.path.join(base_dir, model_rel)),
      dictionary=os.path.abspath(os.path.join(base_dir, dict_rel)),
      wakewords=wakewords,
      discriminants=language_discriminants.get(language, []),
    )

  return settings


def test_wakeword_engine_is_discriminant_fr(config_data):
  engine = WakewordEngine(config_data["fr"])

  # "remi" is a predefined discriminant in the French config (stored without accent)
  assert engine.is_discriminant("remi") is True

  # "oremi" is the wakeword, not a discriminant
  assert engine.is_discriminant("oremi") is False

  # Repeated-word phrases are always discriminants
  assert engine.is_discriminant("test test") is True
  assert engine.is_discriminant("test hello") is False


def test_wakeword_engine_is_discriminant_en(config_data):
  engine = WakewordEngine(config_data["en"])

  # English config has no explicit discriminants
  assert engine.is_discriminant("rémi") is False
  assert engine.is_discriminant("oremi") is False
  assert engine.is_discriminant("hello hello") is True
  assert engine.is_discriminant("hello world") is False


def test_wakeword_engine_process_raw_dummy(config_data):
  engine = WakewordEngine(config_data["en"])

  engine.start_utt()

  # Send 1 second of silent mono audio (16000 Hz, 16-bit PCM → 32000 bytes)
  dummy_chunk = b"\x00" * 32000
  sound, score = engine.process_raw(dummy_chunk)

  # Silent/dummy input should not trigger any wakeword
  assert sound is None
  assert score == 0.0

  engine.end_utt()
