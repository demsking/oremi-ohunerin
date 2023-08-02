from pydantic import BaseModel, Field


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
