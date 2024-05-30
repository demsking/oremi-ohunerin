# Copyright 2023 Sébastien Demanou. All Rights Reserved.
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
from dataclasses import dataclass
from dataclasses import field
from typing import Literal
from typing import TypedDict

from dataclasses_json import dataclass_json


SoundType = Literal['sound', 'wakeword']


class DetectedSound(TypedDict):
  type: SoundType
  sound: str
  score: float
  datetime: str


def create_detected_sound_object(
  sound_type: SoundType,
  sound_name: str,
  score: float,
) -> DetectedSound:
  return {
    'type': sound_type,
    'sound': sound_name,
    'score': score,
    'datetime': datetime.datetime.now().isoformat(),
  }


@dataclass_json
@dataclass
class InitMessage:
  type: Literal['init']
  language: Literal['fr', 'en']
  features: list[Literal['wakeword-detection', 'sound-detection']] = field(default_factory=lambda: [
    'wakeword-detection',
    'sound-detection',
  ])


@dataclass_json
@dataclass
class ServerInitMessage:
  type: Literal['init']
  server: str
  status: str
  languages: list[str]


@dataclass_json
@dataclass
class DictionaryEntry:
  """Class representing a dictionary entry."""

  word: str
  """The word in the dictionary entry."""

  phones: list[str]
  """The list of phonemes for the word."""


@dataclass_json
@dataclass
class WakewordSetting:
  """Settings for the wake word detection."""

  model: str
  """Directory containing the acoustic model files."""

  dictionary: str
  """Dictionary filename."""

  discriminants: list[DictionaryEntry]
  """List of DictionaryEntry objects representing the discriminants."""

  wakewords: list[DictionaryEntry]
  """List of DictionaryEntry objects representing the wakewords."""

  @classmethod
  def from_dict(cls, data: dict):
    discriminants = [DictionaryEntry.from_dict(item) for item in data['discriminants']]  # type: ignore
    wakewords = [DictionaryEntry.from_dict(item) for item in data['wakewords']]  # type: ignore
    return cls(data['model'], data['dictionary'], discriminants, wakewords)
