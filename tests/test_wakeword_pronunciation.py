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

from ohunerin.core.package import MODELS_DIR
from ohunerin.engines.wakeword import KWS_THRESHOLD
from ohunerin.models.sound import SoundsConfig
from ohunerin.models.wakeword import WakewordsConfig
from ohunerin.server.http import HttpHandler

# These tests load the real CMU Sphinx models through the same HttpHandler path the
# server uses, so they need the tracked model directories (no network access).

#: The French wake word deliberately listens for the open-mid vowel variant; the
#: pronunciation study measured it as the best single French candidate at 1e-15.
FR_PRIMARY = "oo rr ai mm ii"
FR_ALTERNATES = ["oo rr ei mm ii", "au rr ei mm ii"]

#: English is intentionally left exactly as it was before the French change.
EN_PRIMARY = "OW R EH M IY"
EN_ALTERNATES = ["OW R EY M IY", "AO R EH M IY", "AO R EY M IY"]


@pytest.fixture
def logger():
  return logging.getLogger("test_wakeword_pronunciation")


@pytest.fixture
def raw_config() -> dict:
  """Load the bundled configuration file as the server does."""
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

  with open(os.path.join(base_dir, "config.json"), encoding="utf-8") as file:
    return json.load(file)


@pytest.fixture
def handler(raw_config) -> HttpHandler:
  """Build the HTTP handler that owns the per-language wakeword pools."""
  return HttpHandler(
    WakewordsConfig.model_validate(raw_config),
    SoundsConfig.model_validate(raw_config["sounds"]),
    0.1,
    MODELS_DIR / "yamnet.tflite",
  )


def engine_for(handler: HttpHandler, language: str):
  """Check a production WakewordEngine out of the language pool."""
  engine = handler.get_wakeword_pool(language).acquire(timeout=0)
  assert engine is not None

  return engine


def test_french_wakeword_searches_the_ai_pronunciation(handler, logger):
  """French must be matched against oo rr ai mm ii, not the previous variant."""
  engine = engine_for(handler, "fr")

  assert engine._setting.wakewords[0].phones[0] == FR_PRIMARY
  assert engine._decoder.lookup_word("oremi") == FR_PRIMARY


def test_french_alternates_are_kept_but_not_activated(handler, logger):
  """The other French pronunciations stay in the dictionary and out of the search."""
  engine = engine_for(handler, "fr")

  for index, phones in enumerate(FR_ALTERNATES, start=2):
    assert engine._decoder.lookup_word(f"oremi({index})") == phones

  keyphrases = engine._decoder.get_kws().split("\n")

  assert "oremi" in keyphrases
  assert all("(" not in keyphrase for keyphrase in keyphrases)


def test_english_wakeword_is_unchanged(handler, logger):
  """English keeps its own pronunciation and never inherits the French one."""
  engine = engine_for(handler, "en")

  assert engine._setting.wakewords[0].phones[0] == EN_PRIMARY
  assert engine._decoder.lookup_word("oremi") == EN_PRIMARY
  assert engine._decoder.lookup_word("oremi") != FR_PRIMARY

  for index, phones in enumerate(EN_ALTERNATES, start=2):
    assert engine._decoder.lookup_word(f"oremi({index})") == phones


def test_config_declares_language_specific_pronunciations(raw_config, logger):
  """Guard the configuration itself, not only the decoder it produces."""
  declared = {(entry["language"], entry["word"]): entry["phones"] for entry in raw_config["wakewords"]}

  assert declared[("fr", "oremi")] == [FR_PRIMARY] + FR_ALTERNATES
  assert declared[("en", "oremi")] == [EN_PRIMARY] + EN_ALTERNATES


def test_search_settings_are_unchanged(handler, logger):
  """The threshold, reporting delay and sample rate must not move with the pronunciation."""
  assert KWS_THRESHOLD == 1e-15

  for language in ("fr", "en"):
    config = engine_for(handler, language)._decoder.config

    assert config.get_float("kws_threshold") == KWS_THRESHOLD
    assert config.get_int("kws_delay") == 10
    assert config.get_int("samprate") == 16000


def test_wakeword_engine_api_is_unchanged(handler, logger):
  """process_raw keeps its (word, score) contract; silence still returns nothing."""
  engine = engine_for(handler, "fr")
  engine.start_utt()

  result = engine.process_raw(b"\x00" * 320)

  engine.end_utt()

  assert result == (None, 0.0)
