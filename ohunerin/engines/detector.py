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
from pathlib import Path

from tflite_support.task import audio  # type: ignore
from tflite_support.task import core
from tflite_support.task import processor

from ohunerin.audio.processing import to_ndarray

logger = logging.getLogger(__name__)

__all__ = [
  "DetectorConsumer",
  "DetectorEngine",
]


class DetectorEngine:
  """Engine for sound classification using TFLite audio task classifier."""

  def __init__(
    self,
    model: Path,
    *,
    score_threshold: float = 0.1,
    num_threads: int = -1,
    allowlist: list[str] | None = None,
    denylist: list[str] | None = None,
  ) -> None:
    if score_threshold < 0 or score_threshold > 1.0:
      raise ValueError("Score threshold must be between (inclusive) 0 and 1.")

    # Initialize the audio classification model.
    base_options = core.BaseOptions(
      file_name=str(model),
      use_coral=False,
      num_threads=num_threads,
    )

    classification_options = processor.ClassificationOptions(
      max_results=1,
      score_threshold=score_threshold,
      category_name_allowlist=allowlist if allowlist else None,
      category_name_denylist=denylist if denylist else None,
    )

    options = audio.AudioClassifierOptions(
      base_options=base_options,
      classification_options=classification_options,
    )

    self.classifier = audio.AudioClassifier.create_from_options(options)
    self.tensor_audio = self.classifier.create_input_tensor_audio()


class DetectorConsumer:
  """Consumes audio data from a detector engine and performs sound classification."""

  def __init__(self, detector: DetectorEngine) -> None:
    """Initialize the DetectorConsumer.

    Args:
      detector (DetectorEngine): The audio detector engine.
      logger (logging.Logger | None): Optional logger instance.
    """
    self._detector = detector

    # Initialize the audio classification buffer.
    self._buffer = bytearray(15600)
    self._buffer_index = 0

  def reset_buffer(self) -> None:
    """Reset the audio classification buffer index to 0."""
    self._buffer_index = 0

  def _classify_audio(self, chunk: bytes) -> tuple[str | None, float]:
    """Classify audio data and process detected sounds.

    Args:
      chunk (bytes): The audio chunk in bytes format.
    """
    audio_array = to_ndarray(chunk, 1)
    self._detector.tensor_audio.load_from_array(audio_array)
    result = self._detector.classifier.classify(self._detector.tensor_audio)

    if len(result.classifications) > 0 and len(result.classifications[0].categories) > 0:
      sound = result.classifications[0].categories[0]

      logger.debug(sound)
      return sound.category_name.lower(), sound.score

    return None, 0.0

  def process_raw(self, chunk: bytes) -> tuple[str | None, float]:
    """Process raw mono audio data and perform sound classification.

    Args:
      chunk (bytes): The raw mono audio data chunk to process.
    """
    for byte in chunk:
      self._buffer[self._buffer_index] = byte
      self._buffer_index += 1

      if self._buffer_index == len(self._buffer):
        result = self._classify_audio(bytes(self._buffer))
        self.reset_buffer()
        return result

    return None, 0.0
