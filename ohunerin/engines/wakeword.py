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
import time

from pocketsphinx import Config  # type: ignore[import-untyped]
from pocketsphinx import Decoder

from ohunerin.core.package import APP_NAME
from ohunerin.models.wakeword import DictionaryEntry
from ohunerin.models.wakeword import WakewordSetting

logger = logging.getLogger(__name__)

__all__ = [
  "DEFAULT_DECODER_POOL_SIZE",
  "KWS_THRESHOLD",
  "WakewordEngine",
  "WakewordPool",
  "WakewordSetting",
]

#: PocketSphinx keyword-spotting threshold (-kws_threshold).
#:
#: kws_search.c reports a keyphrase while
#: keyword_score - best_phone_loop_score >= log(kws_threshold) >> SENSCR_SHIFT,
#: so a *smaller* value is more permissive (PocketSphinx its own default is
#: 1e-30) and a larger value is stricter. The historical hardcoded value,
#: 1e-10, sat inside the score distribution of correctly-spoken wake words:
#: measured on 16 kHz TTS speech with additive white noise (5 seeds per point),
#: the French model detected only 1/5 to 4/5 utterances at 30-40 dB SNR and both
#: models collapsed at 15-10 dB. 1e-15 restores 5/5 detection down to 20 dB SNR
#: for both language models while still rejecting all 29 measured negative
#: phrases (15 EN / 14 FR, including the remi discriminant and the
#: phonetically close "aurora", "harmony" and "remember"); 1e-20 and 1e-30
#: start firing on those negatives. Do not tighten this value again without
#: re-running benchmarks/bench_wakeword.py.
KWS_THRESHOLD = 1e-15

#: Maximum number of PocketSphinx decoders kept alive per language.
#:
#: A decoder owns mutable native state -- the open utterance -- that cannot be
#: multiplexed: PocketSphinx rejects a second start_utt() while one is active,
#: and detections belong to whichever stream fed the decoder. Decoders are
#: therefore checked out per connection for the whole session. They cost
#: ~80-200 ms and ~20-22 MB each, so the pool is bounded and connections that
#: cannot get one are rejected instead of growing without limit.
DEFAULT_DECODER_POOL_SIZE = 4


def is_discriminant_word(setting: WakewordSetting, word: str) -> bool:
  """Check whether a word is a configured or structural discriminant.

  Args:
    setting (WakewordSetting): The language setting owning the discriminants.
    word (str): The hypothesis string to test.

  Returns:
    bool: True when the hypothesis must not trigger a wake-word event.
  """
  # Check against predefined discriminants
  result = any(item for item in setting.discriminants if item.word == word)

  if not result:
    # Check for space and equality of parts
    if " " in word:
      part1, part2 = word.split(" ", 1)  # split into two parts only
      return part1 == part2

  return result


class WakewordEngine:
  """PocketSphinx wake word decoder owning a single native utterance.

  One instance must be used by one connection at a time. PocketSphinx keeps the
  in-progress utterance in native state, so sharing an instance across
  connections mixes their audio and lets one connection end_utt() abort another
  connection stream. Use :class:`WakewordPool` to obtain an instance per
  connection instead of sharing one.
  """

  def __init__(self, setting: WakewordSetting) -> None:
    self._setting = setting
    # Defensive: a decoder is leased to a single connection, but every native
    # call is still serialized so a misuse cannot corrupt native state.
    self._lock = threading.Lock()
    self._utterance_active = False

    config = Config(
      lm=None,
      hmm=setting.model,
      dict=setting.dictionary,
      kws_threshold=KWS_THRESHOLD,
    )

    self._decoder = Decoder(config)
    self._configure_keyphrases()

  def _configure_keyphrases(self) -> None:
    """Configures the keyphrases for the wake word detection.

    Exactly one keyphrase is written per configured word: the bare word. The
    word(2) / word(3) alternates are deliberately left out of the search.
    PocketSphinx resolves a keyphrase with dict_wordid() + dict_pron()
    (src/kws_search.c), which returns the primary dictionary pronunciation, and
    the primary is the first entry registered by _add_dictionary_entry. So the
    pronunciation a wake word is actually matched against is phones[0] in
    config.json; the remaining pronunciations stay available in the dictionary
    but are never searched.

    Reordering phones therefore changes what the decoder listens for, which is
    how the French "oremi" entry is tuned (oo rr ai mm ii first). See
    DOCUMENTATION.md, section "The wakewords Section".
    """
    temp_dir = tempfile.mkdtemp()
    filename = os.path.join(temp_dir, "keyphrases.list")

    logger.debug(f"Creating keyphrases file {filename}")
    with open(filename, "w", encoding="utf-8") as file:
      for entry in self._setting.wakewords + self._setting.discriminants:
        # Bare word on purpose: this is the only pronunciation KWS searches.
        file.write(f"{entry.word}\n")
        self._add_dictionary_entry(entry)

    self._decoder.add_kws(APP_NAME, filename)
    self._decoder.activate_search(APP_NAME)

  def _add_dictionary_entry(self, entry: DictionaryEntry) -> None:
    """Adds a new entry to the wake word dictionary.

    entry.phones[0] is registered under the bare entry.word and becomes the
    pronunciation the keyphrase is matched against. The remaining entries are
    registered as word(2), word(3), ... alternates: they can be listed with
    lookup_word and are kept for future use, but they are not part of the KWS
    search unless a keyphrase names them explicitly.

    Args:
      entry (DictionaryEntry): The entry to add to the dictionary.
    """
    for index, phone in enumerate(entry.phones):
      logger.debug(f'Adding new word "{entry.word}" ({phone}) to the dictionary')

      word = entry.word if index == 0 else f"{entry.word}({index + 1})"

      try:
        self._decoder.add_word(word, phone)
      except RuntimeError as error:
        # Words already present in the acoustic model dictionary (for example
        # the "remi" discriminant in the English dictionary) cannot be added
        # again; the existing pronunciation is used instead.
        logger.debug(f'Could not add word "{word}": {error}')

  def is_discriminant(self, word: str) -> bool:
    """Checks whether a given word is a discriminant.

    Args:
      word (str): The word to check.

    Returns:
      bool: True if the word is a discriminant, otherwise False.
    """
    return is_discriminant_word(self._setting, word)

  def _begin_utterance(self) -> None:
    """Start a fresh utterance; the caller must hold the lock.

    PocketSphinx keeps CMN statistics inside the feature extractor for the
    whole decoder lifetime and ps_start_utt does not reset them: every
    utterance is folded into a running mean, so the acoustic features slowly
    drift and the keyword score eventually falls below the threshold forever.
    Measured with the French model, a reused decoder reported 5/30 wake words
    and then nothing, while the same decoder detected 100/100 once the feature
    extractor was reinitialized between utterances. ps_reinit_feat builds the
    extractor from the model own feat.params (it does not change the model
    configuration) and costs ~0.02 ms, so the decoder behaves exactly like a
    freshly built one for every utterance.
    """
    self._decoder.reinit_feat()
    self._decoder.start_utt()
    self._utterance_active = True

  def start_utt(self) -> None:
    """Starts a new utterance for wake word detection.

    Idempotent: starting an already running utterance is a no-op instead of a
    native error, so a decoder handed back to the pool can always be reused.
    """
    with self._lock:
      if self._utterance_active:
        return

      self._begin_utterance()

  def end_utt(self) -> None:
    """Ends the current utterance for wake word detection.

    Idempotent: ending an idle decoder is a no-op.
    """
    with self._lock:
      if not self._utterance_active:
        return

      self._decoder.end_utt()
      self._utterance_active = False

  def process_raw(self, chunk: bytes) -> tuple[str | None, float]:
    """Process raw PCM audio bytes for wake word recognition.

    The utterance is kept open across calls: PocketSphinx keeps the acoustic
    context of the in-progress keyphrase, so a WebSocket frame boundary in the
    middle of a wake word does not reset or damage the search.
    """
    with self._lock:
      if not self._utterance_active:
        self._begin_utterance()

      self._decoder.process_raw(chunk, False, False)

      hypothesis = self._decoder.hyp()

      if hypothesis:
        is_discriminant = self.is_discriminant(hypothesis.hypstr)

        self._decoder.end_utt()
        self._begin_utterance()

        if not is_discriminant:
          logger.info(f"Wakeword detected: {hypothesis.hypstr}, score {hypothesis.score:.2f}")

          return hypothesis.hypstr, hypothesis.score

        logger.warning(f"Discriminant wakeword detected: {hypothesis.hypstr}, score {hypothesis.score:.2f}")

    return None, 0.0


class WakewordPool:
  """Bounded, thread-safe pool of PocketSphinx decoders for one language.

  Decoders are checked out for the lifetime of a connection and returned with
  :meth:`release`, which resets the native utterance so the next lease starts
  clean. Building a decoder is expensive (~80-200 ms, ~20-22 MB), so idle
  decoders are reused instead of being destroyed, and the pool never grows past
  :data:`DEFAULT_DECODER_POOL_SIZE` unless the caller asks for more.
  """

  def __init__(self, setting: WakewordSetting, size: int = DEFAULT_DECODER_POOL_SIZE) -> None:
    """Initialize the pool.

    Args:
      setting (WakewordSetting): Language-specific model, dictionary and words.
      size (int): Maximum number of decoders ever built for this language.
    """
    self.setting = setting
    self._size = max(1, size)
    self._condition = threading.Condition()
    self._idle: list[WakewordEngine] = []
    self._leased: set[WakewordEngine] = set()
    self._created = 0

  @property
  def size(self) -> int:
    """Maximum number of decoders this pool may build."""
    return self._size

  @property
  def created(self) -> int:
    """Number of decoders built so far."""
    with self._condition:
      return self._created

  @property
  def in_use(self) -> int:
    """Number of decoders currently checked out by a connection."""
    with self._condition:
      return len(self._leased)

  @property
  def available(self) -> int:
    """Number of idle decoders ready to be checked out."""
    with self._condition:
      return len(self._idle)

  def is_discriminant(self, word: str) -> bool:
    """Checks whether a given word is a discriminant."""
    return is_discriminant_word(self.setting, word)

  def acquire(self, timeout: float | None = None) -> WakewordEngine | None:
    """Check out a decoder, building one while the pool has spare capacity.

    Args:
      timeout (float | None): Seconds to wait for a decoder when the pool is at
        capacity. None waits indefinitely, 0 never waits.

    Returns:
      WakewordEngine | None: An idle decoder, or None when the pool stayed at
      capacity for the whole timeout.
    """
    deadline = None if timeout is None else time.monotonic() + timeout

    with self._condition:
      while True:
        if self._idle:
          engine = self._idle.pop()
          self._leased.add(engine)
          return engine

        if self._created < self._size:
          self._created += 1
          break

        remaining = None if deadline is None else deadline - time.monotonic()

        if remaining is not None and remaining <= 0:
          return None

        self._condition.wait(remaining)

    try:
      engine = WakewordEngine(self.setting)
    except Exception:
      with self._condition:
        self._created -= 1
        self._condition.notify()
      raise

    with self._condition:
      self._leased.add(engine)

    return engine

  def release(self, engine: WakewordEngine) -> None:
    """Reset a decoder utterance state and return it to the pool.

    Args:
      engine (WakewordEngine): A decoder previously returned by acquire.
    """
    with self._condition:
      if engine not in self._leased:
        logger.warning("Attempted to release a wake-word decoder that was not checked out")
        return

      self._leased.discard(engine)

    engine.end_utt()

    with self._condition:
      self._idle.append(engine)
      self._condition.notify()
