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

import numpy as np

logger = logging.getLogger(__name__)

__all__ = [
  "to_ndarray",
]


def to_ndarray(data: bytes, num_channels: int) -> np.ndarray:
  """Converts audio data from a byte string to a NumPy array of float64 values normalized to [-1.0, 1.0].

  Args:
    data (bytes): Raw PCM audio bytes (int16 format).
    num_channels (int): Number of audio channels.

  Returns:
    np.ndarray: Reshaped, normalized float64 NumPy array.
  """
  audio_array = np.frombuffer(data, dtype=np.int16)
  audio_float = audio_array.astype(np.float64) / 32768.0
  return audio_float.reshape(-1, num_channels)
