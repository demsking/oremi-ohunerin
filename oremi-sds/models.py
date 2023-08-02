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
from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class DetectedSound(TypedDict):
  type: Literal['sound']
  sound: str
  score: float
  datetime: str


def create_detected_sound_object(sound_name: str, score: float) -> DetectedSound:
  return {
    'type': 'sound',
    'sound': sound_name,
    'score': score,
    'datetime': datetime.datetime.now().isoformat(),
  }


class InitMessage(BaseModel):
  type: Literal['init']
  num_channels: int
  samplerate: int
  blocksize: int
  language: Literal['fr', 'en']
  features: list[Literal['wakeword-detector', 'sound-detector']] = Field(min_items = 1, default_factory = lambda: [
    'wakeword-detector',
    'sound-detector',
  ])


class DictionaryEntry(BaseModel):
  """Class representing a dictionary entry."""

  word: str
  """The word in the dictionary entry."""

  phones: list[str]
  """The list of phonemes for the word."""


class WakewordSetting(BaseModel):
  """Settings for the wake word detection."""

  model: str
  """Directory containing the acoustic model files."""

  dictionary: str
  """Dictionary filename."""

  wakewords: list[DictionaryEntry] = Field(min_items = 1)
  """List of DictionaryEntry objects representing the wakewords."""

  discriminants: list[DictionaryEntry]
  """List of DictionaryEntry objects representing the discriminants."""


Config = dict[str, WakewordSetting]
