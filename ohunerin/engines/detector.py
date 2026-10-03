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
import threading
from pathlib import Path

import numpy as np
from tflite_support.task import audio  # type: ignore
from tflite_support.task import core
from tflite_support.task import processor

from ohunerin.audio.processing import to_ndarray

logger = logging.getLogger(__name__)

__all__ = [
  "DEFAULT_MAX_INFERENCE_THREADS",
  "WINDOW_BYTES",
  "DetectorConsumer",
  "DetectorEngine",
  "recommended_num_threads",
]

#: Number of PCM bytes accumulated by :class:`DetectorConsumer` before classifying.
#:
#: This is the historical contract: 15 600 bytes = 7 800 mono int16 samples,
#: i.e. 0.4875 s at 16 kHz. YAMNet itself wants a 0.975 s window (15 600
#: *samples* = 31 200 bytes); the remaining half comes from ``TensorAudio``,
#: whose buffer slides forward by one consumer window on every
#: ``load_from_array`` call. Keeping this value unchanged preserves the exact
#: audio windows the model has always been fed.
WINDOW_BYTES = 15600

#: Upper bound for the TFLite interpreter thread count.
#:
#: TFLite's XNNPACK delegate spins up ``num_threads`` workers per interpreter.
#: Feeding it ``os.cpu_count()`` -- the historical default -- makes those workers
#: fight for cores: benchmarked inference latency degrades by two orders of
#: magnitude once the thread count approaches or exceeds the CPU allocation
#: (185 ms vs 4 ms per window on a 20-core host). YAMNet is small enough that a
#: handful of threads already saturates the useful parallelism.
DEFAULT_MAX_INFERENCE_THREADS = 4


def recommended_num_threads() -> int:
  """Return a bounded TFLite thread count suitable for real-time audio inference."""
  try:
    available = len(os.sched_getaffinity(0))
  except (AttributeError, OSError):  # pragma: no cover - platforms without affinity
    available = os.cpu_count() or 1

  return max(1, min(DEFAULT_MAX_INFERENCE_THREADS, available))


class DetectorEngine:
  """Engine for sound classification using TFLite audio task classifier.

  The interpreter, its XNNPACK delegate and the ``TensorAudio`` scratch buffer
  are not thread-safe. A single engine is shared by every connection and guarded
  by an internal lock, so callers must use :meth:`classify_window` instead of
  touching ``classifier`` / ``tensor_audio`` directly.
  """

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
    self._lock = threading.Lock()

  def classify_window(self, audio_array: np.ndarray) -> tuple[str | None, float]:
    """Classify one normalized audio window and return ``(label, score)``.

    Args:
      audio_array (np.ndarray): Normalized audio shaped ``(samples, channels)``.

    Returns:
      tuple[str | None, float]: Lowercased label and score, or ``(None, 0.0)``
      when the model produced no category above the score threshold.
    """
    with self._lock:
      self.tensor_audio.load_from_array(audio_array)
      result = self.classifier.classify(self.tensor_audio)

    if len(result.classifications) > 0 and len(result.classifications[0].categories) > 0:
      sound = result.classifications[0].categories[0]

      logger.debug(sound)
      return sound.category_name.lower(), sound.score

    return None, 0.0


class DetectorConsumer:
  """Buffers one audio stream and classifies it when a full window is available.

  A consumer is cheap -- one :data:`WINDOW_BYTES` bytearray -- and holds the
  buffering state of a single connection. Use one consumer per connection and
  share the expensive :class:`DetectorEngine` between them.
  """

  def __init__(self, detector: DetectorEngine) -> None:
    """Initialize the DetectorConsumer.

    Args:
      detector (DetectorEngine): The audio detector engine.
    """
    self._detector = detector

    # Initialize the audio classification buffer.
    self._buffer = bytearray(WINDOW_BYTES)
    self._buffer_index = 0

  def reset_buffer(self) -> None:
    """Reset the audio classification buffer index to 0."""
    self._buffer_index = 0

  def _classify_audio(self, chunk: bytes | bytearray) -> tuple[str | None, float]:
    """Classify audio data and process detected sounds.

    Args:
      chunk (bytes | bytearray): The audio chunk to classify.
    """
    # ``to_ndarray`` copies before the buffer is reused, so the bytearray can be
    # passed directly and the extra ``bytes(...)`` copy is avoided.
    return self._detector.classify_window(to_ndarray(chunk, 1))

  def process_raw(self, chunk: bytes) -> tuple[str | None, float]:
    """Process raw mono audio data and perform sound classification.

    The write is a single slice assignment instead of a Python-level byte loop;
    a 8,000-byte chunk costs ~2 us instead of ~800 us. Bytes past the end of the
    window are dropped, matching the historical behaviour.

    Args:
      chunk (bytes): The raw mono audio data chunk to process.
    """
    size = len(chunk)
    remaining = WINDOW_BYTES - self._buffer_index

    if size >= remaining:
      self._buffer[self._buffer_index:] = chunk[:remaining]
      self._buffer_index = WINDOW_BYTES
      result = self._classify_audio(self._buffer)
      self.reset_buffer()
      return result

    end = self._buffer_index + size
    self._buffer[self._buffer_index:end] = chunk
    self._buffer_index = end

    return None, 0.0
