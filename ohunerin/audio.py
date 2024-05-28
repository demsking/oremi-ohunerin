# Copyright 2023 Sébastien Demanou. All Rights Reserved.
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
import numpy as np

__all__ = [
  'to_ndarray',
]


def to_ndarray(data: bytes, num_channels: int):
  """
  Converts audio data from a byte string to a NumPy array of float64 values.

  Args:
    data (bytes): A byte string containing audio data with a sample rate of 16000 and a data type of int16.

  Returns:
    np.ndarray: A NumPy array of float64 values representing the audio data, normalized to the range [-1.0, 1.0].
  """
  # Create a NumPy array from the byte string
  audio_array = np.frombuffer(data, dtype=np.int16)

  # Convert the data type of the array to float
  audio_array = audio_array.astype(np.float64)

  # Normalize the audio data to the range [-1.0, 1.0]
  audio_array /= 32768.0

  # Reshape the data to separate the channels
  audio_array = audio_array.reshape(-1, num_channels)

  return audio_array
