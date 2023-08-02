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
