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
import logging
import os
import tempfile
import threading

from pocketsphinx import Config  # type: ignore[import-untyped]
from pocketsphinx import Decoder

from ohunerin.core.package import APP_NAME
from ohunerin.models.wakeword import DictionaryEntry
from ohunerin.models.wakeword import WakewordSetting

logger = logging.getLogger(__name__)

__all__ = [
  "WakewordEngine",
  "WakewordSetting",
]


class WakewordEngine:
  """Class for performing wake word detection using PocketSphinx."""

  def __init__(self, setting: WakewordSetting) -> None:
    self._setting = setting
    # A PocketSphinx decoder owns mutable native state (the current utterance).
    # The engine is shared by every connection on the same language, so all
    # decoder calls are serialized to avoid concurrent native state mutation.
    self._lock = threading.Lock()

    config = Config(
      lm=None,
      hmm=setting.model,
      dict=setting.dictionary,
      kws_threshold=1e-10,
    )

    self._decoder = Decoder(config)
    self._configure_keyphrases()

  def _configure_keyphrases(self) -> None:
    """Configures the keyphrases for the wake word detection."""
    temp_dir = tempfile.mkdtemp()
    filename = os.path.join(temp_dir, "keyphrases.list")

    logger.info(f"Creating keyphrases file {filename}")
    with open(filename, "w", encoding="utf-8") as file:
      for entry in self._setting.wakewords + self._setting.discriminants:
        file.write(f"{entry.word}\n")
        self._add_dictionary_entry(entry)

    self._decoder.add_kws(APP_NAME, filename)
    self._decoder.activate_search(APP_NAME)

  def _add_dictionary_entry(self, entry: DictionaryEntry) -> None:
    """Adds a new entry to the wake word dictionary.

    Args:
      entry (DictionaryEntry): The entry to add to the dictionary.
    """
    for index, phone in enumerate(entry.phones):
      logger.info(f'Adding new word "{entry.word}" ({phone}) to the dictionary')

      word = entry.word if index == 0 else f"{entry.word}({index + 1})"

      try:
        self._decoder.add_word(word, phone)
      except RuntimeError as error:
        logger.error(error)

  def is_discriminant(self, word: str) -> bool:
    """Checks whether a given word is a discriminant.

    Args:
      word (str): The word to check.

    Returns:
      bool: True if the word is a discriminant, otherwise False.
    """
    # Check against predefined discriminants
    result = any(item for item in self._setting.discriminants if item.word == word)

    if not result:
      # Check for space and equality of parts
      if " " in word:
        part1, part2 = word.split(" ", 1)  # split into two parts only
        return part1 == part2

    return result

  def start_utt(self) -> None:
    """Starts a new utterance for wake word detection."""
    with self._lock:
      self._decoder.start_utt()

  def end_utt(self) -> None:
    """Ends the current utterance for wake word detection."""
    with self._lock:
      self._decoder.end_utt()

  def process_raw(self, chunk: bytes) -> tuple[str | None, float]:
    """Process raw PCM audio bytes for wake word recognition."""
    with self._lock:
      self._decoder.process_raw(chunk, False, False)

      hypothesis = self._decoder.hyp()

      if hypothesis:
        is_discriminant = self.is_discriminant(hypothesis.hypstr)

        self._decoder.end_utt()
        self._decoder.start_utt()

        if not is_discriminant:
          return hypothesis.hypstr, hypothesis.score

        logger.warning(f"Discriminant wakeword detected: {hypothesis.hypstr}, score {hypothesis.score:.2f}")

    return None, 0.0
