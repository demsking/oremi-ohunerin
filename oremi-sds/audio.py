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


def resample_audio(audio_data: bytes, original_sample_rate: int, target_sample_rate: int) -> bytes:
  """
  Resample audio data from the original sample rate to the target sample rate.

  Args:
    audio_data (bytes): Audio data in bytes.
    original_sample_rate (int): The original sample rate of the audio data.
    target_sample_rate (int): The desired target sample rate.

  Returns:
    bytes: Resampled audio data in bytes if resampling is performed; otherwise, the original audio data.
  """
  if original_sample_rate != target_sample_rate:
    # Convert bytes to numpy array with dtype int16
    audio_array = np.frombuffer(audio_data, dtype = np.int16)

    # Calculate the resampling ratio
    resample_ratio = target_sample_rate / original_sample_rate

    # Perform the resampling
    resampled_data = signal.resample(audio_array, int(len(audio_array) * resample_ratio))

    # Convert the resampled numpy array back to bytes
    resampled_bytes = resampled_data.astype(np.int16).tobytes()
    return resampled_bytes
  # If the original sample rate matches the target sample rate, return the original audio data.
  return audio_data


def multi_channel_to_mono(data: bytes, num_channels: int) -> bytes:
  """
  Converts multi-channel audio data in bytes format to mono audio data.

  Args:
    data (bytes): The multi-channel audio data in bytes format.
    num_channels (int): The number of audio channels.

  Returns:
    bytes: The converted mono audio data in bytes format.
  """
  audio_array = np.frombuffer(data, dtype=np.int16)
  reshaped_audio = audio_array.reshape(-1, num_channels)

  mono_array = np.mean(reshaped_audio, axis=1, dtype=np.int16)
  mono_bytes = mono_array.tobytes()

  return mono_bytes


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
