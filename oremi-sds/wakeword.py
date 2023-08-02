import os
import tempfile

from pocketsphinx import Config, Decoder

from .models import DictionaryEntry, WakewordSetting
from .trace import Trace
from .vars import APP_ID, ENCODING

__all__ = [
  'WakewordSetting',
  'WakewordEngine',
]


class WakewordEngine:
  """Class for performing wake word detection."""

  def __init__(self, setting: WakewordSetting, logger: Trace):
    self.logger = logger
    self.setting = setting
    config = Config(
      lm = None,
      hmm = setting.model,
      dict = setting.dictionary,
      kws_threshold = 1e-10,
    )

    self.decoder = Decoder(config)
    self.configure_keyphrases()

  def configure_keyphrases(self):
    """Configures the keyphrases for the wake word detection."""
    temp_dir = tempfile.mkdtemp()
    filename = os.path.join(temp_dir, 'keyphrases.list')

    self.logger.info(f'Creating keyphrases file {filename}')
    with open(filename, 'w', encoding = ENCODING) as file:
      for entry in self.setting.wakewords + self.setting.discriminants:
        file.write(f'{entry.word}\n')
        self.add_dictionary_entry(entry)

    self.decoder.add_kws(APP_ID, filename)
    self.decoder.activate_search(APP_ID)

  def add_dictionary_entry(self, entry: DictionaryEntry) -> None:
    """
    Adds a new entry to the wake word dictionary.

    Args:
      entry (DictionaryEntry): The entry to add to the dictionary.
    """
    for index, phone in enumerate(entry.phones):
      self.logger.info(f'Adding new word "{entry.word}" to the dictionary')

      word = entry.word if index == 0 else f'{entry.word}({index + 1})'

      try:
        self.decoder.add_word(word, phone)
      except RuntimeError as error:
        self.logger.error(error)

  def is_discriminant(self, word: str) -> bool:
    """
    Checks whether a given word is a discriminant.

    Args:
        word (str): The word to check.

    Returns:
        bool: True if the word is a discriminant, otherwise False.
    """
    return any(item for item in self.setting.discriminants if item.word == word)

  def start_utt(self) -> None:
    """Starts a new utterance for the wake word detection."""
    self.decoder.start_utt()

  def end_utt(self) -> None:
    """Ends the current utterance for the wake word detection."""
    self.decoder.end_utt()

  def process_raw(self, chunk: bytes) -> float:
    """
    Process a chunk of raw audio data for wakeword detection and return the confidence score.

    This function takes a chunk of raw audio data as input, processes it using the decoder for wakeword
    detection, and returns the confidence score for the detected wakeword.

    Args:
      chunk (bytes): The chunk of raw audio data as bytes.

    Returns:
      float: The confidence score for the detected wakeword. Returns 0.0 if no wakeword is detected.

    Notes:
      The `self.is_discriminant()` method is used to check if the detected wakeword is discriminant
      (similar but should be ignored). If a discriminant wakeword is detected, a warning message
      is logged, and the function returns False.

      The decoder is reset (`self.decoder.end_utt()` and `self.decoder.start_utt()`) after each
      processed chunk to prepare it for the next audio chunk.
    """
    self.decoder.process_raw(chunk, False, False)

    hypothesis = self.decoder.hyp()

    if hypothesis is None:
      return 0.0

    is_discriminant = self.is_discriminant(hypothesis.hypstr)

    self.decoder.end_utt()
    self.decoder.start_utt()

    if is_discriminant:
      self.logger.warning(f'Discriminant wakeword detected: {hypothesis.hypstr}')
      return False

    return hypothesis.score
