# Copyright 2023-2026 Sébastien Demanou. All Rights Reserved.
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
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator


class DictionaryEntry(BaseModel):
  """A word and its phonetic pronunciations."""

  word: str
  """The word to recognise."""

  phones: list[str]
  """One or more phonetic transcriptions for the word."""


class WakewordEntry(BaseModel):
  """A wakeword definition inside the config file."""

  language: str
  """BCP-47 language code (e.g. 'fr', 'en')."""

  word: str
  """The wakeword phrase."""

  phones: list[str]
  """One or more phonetic transcriptions for the wakeword."""

  discriminants: list[DictionaryEntry] = Field(default_factory=list)
  """Words that must NOT trigger detection (false-positive guards)."""


class WakewordDetectionFeature(BaseModel):
  name: Literal["wakeword-detection"]
  language: Literal["fr", "en"]
  wakewords: list[DictionaryEntry] = Field(default_factory=list)
  discriminants: list[DictionaryEntry] = Field(default_factory=list)


class WakewordSetting(BaseModel):
  """Resolved, language-specific settings used to initialise the wakeword engine."""

  model: str
  """Directory containing the acoustic model files."""

  dictionary: str
  """Dictionary filename."""

  discriminants: list[DictionaryEntry]
  """Discriminant words that should NOT trigger detection."""

  wakewords: list[DictionaryEntry]
  """Wakeword phrases that should trigger detection."""


class WakewordsConfig(BaseModel):
  """Configuration model for wakeword definitions."""

  wakewords: list[WakewordEntry] = Field(default_factory=list)
  """All wakeword definitions, grouped by language inside each entry."""

  @model_validator(mode="before")
  @classmethod
  def _preprocess_data(cls, data: Any) -> Any:
    if isinstance(data, list):
      return {"wakewords": data}

    if isinstance(data, dict) and data and "wakewords" not in data:
      return {"wakewords": [data]}

    return data
