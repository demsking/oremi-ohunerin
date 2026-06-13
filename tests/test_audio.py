# Copyright 2026 Sébastien Demanou. All Rights Reserved.
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
import pytest
from ohunerin.audio import to_ndarray


def test_to_ndarray_mono():
  # 16-bit PCM (2 bytes per sample). Let's create 4 samples.
  # 0, 32767, -32768, 16384
  # In 16-bit signed integer little endian:
  # 0 -> \x00\x00
  # 32767 -> \xff\x7f
  # -32768 -> \x00\x80
  # 16384 -> \x00\x40
  data = b"\x00\x00\xff\x7f\x00\x80\x00\x40"
  
  result = to_ndarray(data, num_channels=1)
  
  assert result.shape == (4, 1)
  assert np.isclose(result[0, 0], 0.0)
  assert np.isclose(result[1, 0], 32767.0 / 32768.0)
  assert np.isclose(result[2, 0], -1.0)
  assert np.isclose(result[3, 0], 0.5)


def test_to_ndarray_stereo():
  # 4 samples, 2 channels -> shape (2, 2)
  data = b"\x00\x00\xff\x7f\x00\x80\x00\x40"
  
  result = to_ndarray(data, num_channels=2)
  
  assert result.shape == (2, 2)
  assert np.isclose(result[0, 0], 0.0)
  assert np.isclose(result[0, 1], 32767.0 / 32768.0)
  assert np.isclose(result[1, 0], -1.0)
  assert np.isclose(result[1, 1], 0.5)


def test_to_ndarray_empty():
  result = to_ndarray(b"", num_channels=1)
  assert result.shape == (0, 1)
