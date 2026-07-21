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
import datetime

import pytest
from pydantic import ValidationError

from ohunerin.models.sound import SoundsConfig, create_detected_sound_object
from ohunerin.models.sound import SoundDetectionFeature
from ohunerin.models.wakeword import DictionaryEntry, WakewordDetectionFeature, WakewordEntry, WakewordSetting, WakewordsConfig


def test_create_detected_sound_object():
  obj = create_detected_sound_object("wakeword", "oremi", 0.95)
  assert obj["type"] == "wakeword"
  assert obj["sound"] == "oremi"
  assert obj["score"] == 0.95

  # Validate datetime is in correct ISO format
  dt = datetime.datetime.fromisoformat(obj["datetime"])
  assert isinstance(dt, datetime.datetime)


def test_dictionary_entry_validation():
  entry = DictionaryEntry(word="hello", phones=["H", "EH", "L", "OW"])
  assert entry.word == "hello"
  assert entry.phones == ["H", "EH", "L", "OW"]

  with pytest.raises(ValidationError):
    DictionaryEntry.model_validate({"word": "hello"})  # Missing required field: phones


def test_wakeword_entry_no_discriminants():
  entry = WakewordEntry(language="en", word="oremi", phones=["AO R EY M E"])
  assert entry.language == "en"
  assert entry.word == "oremi"
  assert entry.phones == ["AO R EY M E"]
  assert entry.discriminants == []


def test_wakeword_entry_with_discriminants():
  disc = DictionaryEntry(word="rémi", phones=["rr ei mm ii"])
  entry = WakewordEntry(
    language="fr",
    word="oremi",
    phones=["oo rr ei mm ii"],
    discriminants=[disc],
  )
  assert entry.discriminants == [disc]


def test_wakewords_config_defaults():
  config = WakewordsConfig()
  assert config.wakewords == []


def test_wakewords_config_full():
  raw = {
    "wakewords": [
      {
        "language": "fr",
        "word": "oremi",
        "phones": ["oo rr ei mm ii"],
        "discriminants": [{"word": "rémi", "phones": ["rr ei mm ii"]}],
      },
      {
        "language": "en",
        "word": "oremi",
        "phones": ["AO R EY M E"],
      },
    ],
  }
  config = WakewordsConfig.model_validate(raw)
  assert len(config.wakewords) == 2
  assert config.wakewords[0].language == "fr"
  assert config.wakewords[0].word == "oremi"
  assert len(config.wakewords[0].discriminants) == 1
  assert config.wakewords[0].discriminants[0].word == "rémi"
  assert config.wakewords[1].language == "en"


def test_sound_filter_config():
  # Test with list input
  sf1 = SoundsConfig.model_validate(["Shout", "Laughter"])
  assert sf1.whitelist == ["Shout", "Laughter"]
  assert sf1.blacklist == []
  assert sf1.allowlist == ["Shout", "Laughter"]

  # Test with whitelist/blacklist dict input
  sf2 = SoundsConfig.model_validate({"whitelist": ["Shout"], "blacklist": ["Snoring"]})
  assert sf2.whitelist == ["Shout"]
  assert sf2.blacklist == ["Snoring"]

  # Test with allowlist/denylist dict input
  sf3 = SoundsConfig.model_validate({"allowlist": ["Laughter"], "denylist": ["Crying"]})
  assert sf3.whitelist == ["Laughter"]
  assert sf3.blacklist == ["Crying"]
  assert sf3.allowlist == ["Laughter"]
  assert sf3.denylist == ["Crying"]


def test_wakeword_detection_feature():
  feature = WakewordDetectionFeature(name="wakeword-detection", language="en")
  assert feature.name == "wakeword-detection"
  assert feature.language == "en"
  assert feature.wakewords == []
  assert feature.discriminants == []

  entry = DictionaryEntry(word="hello", phones=["H"])
  feature2 = WakewordDetectionFeature(name="wakeword-detection", language="fr", wakewords=[entry], discriminants=[entry])
  assert feature2.wakewords == [entry]
  assert feature2.discriminants == [entry]


def test_sound_detection_feature():
  feature = SoundDetectionFeature(name="sound-detection")
  assert feature.name == "sound-detection"
  assert feature.allowlist == []

  feature2 = SoundDetectionFeature(name="sound-detection", allowlist=["dog", "cat"])
  assert feature2.allowlist == ["dog", "cat"]


def test_wakeword_setting_and_copy():
  entry_wake = DictionaryEntry(word="oremi", phones=["O", "R", "E", "M", "I"])
  entry_disc = DictionaryEntry(word="remi", phones=["R", "E", "M", "I"])

  setting = WakewordSetting(
    model="/path/to/model", dictionary="/path/to/dict", discriminants=[entry_disc], wakewords=[entry_wake]
  )

  assert setting.model == "/path/to/model"
  assert setting.dictionary == "/path/to/dict"
  assert setting.discriminants == [entry_disc]
  assert setting.wakewords == [entry_wake]

  # Test copy method
  copied = setting.copy()
  assert copied is not setting
  assert copied.model == setting.model
  assert copied.dictionary == setting.dictionary
  assert copied.discriminants == setting.discriminants
  assert copied.wakewords == setting.wakewords

  # Verify deep copy of entries (independent lists/objects)
  assert copied.discriminants is not setting.discriminants
  assert copied.discriminants[0] is not setting.discriminants[0]
  assert copied.wakewords is not setting.wakewords
  assert copied.wakewords[0] is not setting.wakewords[0]
