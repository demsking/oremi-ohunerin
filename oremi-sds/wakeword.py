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

  def process_raw(self, chunk: bytes) -> bool:
    """
    Processes a chunk of audio data to detect a wakeword.

    This function takes a chunk of audio data as input, processes it using the
    decoder, and then checks if a wakeword or a discriminant wakeword is detected.

    Args:
      chunk (bytes): The chunk of audio data as bytes.

    Returns:
      bool: True if a wakeword is detected, False otherwise.

    Notes:
      A discriminant wakeword refers to a wakeword that is similar to the actual
      wakeword but should be ignored. When a discriminant wakeword is detected,
      it is logged as a warning, and the processing starts again.
    """
    self.decoder.process_raw(chunk, False, False)

    hypothesis = self.decoder.hyp()

    if hypothesis is None:
      return False

    is_discriminant = self.is_discriminant(hypothesis.hypstr)

    self.decoder.end_utt()
    self.decoder.start_utt()

    if is_discriminant:
      self.logger.warn(f'Discriminant wakeword detected: {hypothesis.hypstr}')
    else:
      self.logger.debug(f'Wakeword detected: {hypothesis.hypstr}')

    return not is_discriminant
