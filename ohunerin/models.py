# Copyright 2023-2025 Sébastien Demanou. All Rights Reserved.
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
from typing import Literal
from typing import TypedDict

from pydantic import BaseModel
from pydantic import Field

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


class DictionaryEntry(BaseModel):
  word: str
  phones: list[str]


class WakewordDetectionFeature(BaseModel):
  name: Literal['wakeword-detection']
  language: Literal['fr', 'en']
  wakewords: list[DictionaryEntry] = Field(default_factory=list)
  discriminants: list[DictionaryEntry] = Field(default_factory=list)


class SoundDetectionFeature(BaseModel):
  name: Literal['sound-detection']
  allowlist: list[str] = Field(default_factory=list)


class ClientInitMessage(BaseModel):
  type: Literal['init']
  features: list[WakewordDetectionFeature | SoundDetectionFeature]


class ServerInitMessage(BaseModel):
  type: Literal['init']
  server: str
  available_languages: list[str]


class ServerReadyMessage(BaseModel):
  type: Literal['ready']


class WakewordSetting(BaseModel):
  """Settings for the wake word detection."""

  model: str
  """Directory containing the acoustic model files."""

  dictionary: str
  """Dictionary filename."""

  discriminants: list[DictionaryEntry]
  """List of Discriminant objects representing the discriminants."""

  wakewords: list[DictionaryEntry]
  """List of Wakeword objects representing the wakewords."""

  def copy(self) -> 'WakewordSetting':
    return WakewordSetting(
      model=self.model,
      dictionary=self.dictionary,
      discriminants=[DictionaryEntry(word=entry.word, phones=entry.phones) for entry in self.discriminants],
      wakewords=[DictionaryEntry(word=entry.word, phones=entry.phones) for entry in self.wakewords],
    )
