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
from scipy import signal  # type: ignore

__all__ = [
  'reduce_noise',
  'to_ndarray',
]


def reduce_noise(data: np.ndarray, sample_rate: int):
  """
  Reduce noise from the data using a high-pass filter.

  Args:
    data (np.ndarray): The audio data to filter.
    sample_rate (int): The sample rate of the audio data.

  Returns:
    np.ndarray: The filtered audio data.

  Raises:
    ValueError: If the sample rate is not positive.
  """
  if sample_rate <= 0:
    raise ValueError('The sample rate must be positive.')

  numerator_b, denominator_a = signal.butter(10, 2000/(sample_rate/2), btype='highpass')
  yf = signal.lfilter(numerator_b, denominator_a, data)
  return yf


def to_16bit_mono(data: np.ndarray) -> bytes:
  """
  Rescale the data to 16-bit signed integers and convert it to binary data.

  Args:
    data (np.ndarray): The audio data to convert.

  Returns:
    bytes: The binary data representing the audio data.

  Raises:
    ValueError: If the data is not two-dimensional.
  """
  if data.ndim != 2:
    raise ValueError('The data must be two-dimensional.')

  # Rescale the values to fit within the range of 16-bit signed integers (-32768 to 32767)
  rescaled_arr = (data * 32767).astype(np.int16)

  # Convert the rescaled ndarray to binary data
  return rescaled_arr.tobytes()


def to_ndarray(data: bytes, num_channels: int):
  """
  Converts audio data from a byte string to a NumPy array of float64 values.

  Args:
    data (bytes): A byte string containing audio data with a sample rate of 16000 and a data type of int16.

  Returns:
    np.ndarray: A NumPy array of float64 values representing the audio data, normalized to the range [-1.0, 1.0].
  """
  # Create a NumPy array from the byte string
  audio_array = np.frombuffer(data, dtype = np.int16)

  # Convert the data type of the array to float
  audio_array = audio_array.astype(np.float64)

  # Normalize the audio data to the range [-1.0, 1.0]
  audio_array /= 32768.0

  # Reshape the data to separate the channels
  audio_array = audio_array.reshape(-1, num_channels)

  return audio_array
