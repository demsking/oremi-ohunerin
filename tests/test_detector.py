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
import logging
import os

import pytest

from ohunerin.engines.detector import DetectorConsumer
from ohunerin.engines.detector import DetectorEngine


@pytest.fixture
def logger():
  return logging.getLogger("test_detector")


@pytest.fixture
def data_path():
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  return os.path.join(base_dir, "models", "yamnet.tflite")


def test_detector_engine_invalid_threshold(data_path):
  with pytest.raises(ValueError, match="Score threshold must be between"):
    DetectorEngine(data_path, score_threshold=-0.1)

  with pytest.raises(ValueError, match="Score threshold must be between"):
    DetectorEngine(data_path, score_threshold=1.1)


def test_detector_engine_init(data_path):
  engine = DetectorEngine(data_path, score_threshold=0.1)
  assert engine.classifier is not None
  assert engine.tensor_audio is not None


def test_detector_consumer_buffer_flow(data_path):
  engine = DetectorEngine(data_path, score_threshold=0.1)
  consumer = DetectorConsumer(engine)

  # Check initial buffer state
  assert len(consumer._buffer) == 15600
  assert consumer._buffer_index == 0

  # Send small chunk, should not trigger classification
  chunk = b"\x00" * 100
  sound, score = consumer.process_raw(chunk)
  assert sound is None
  assert score == 0.0
  assert consumer._buffer_index == 100

  # Reset buffer
  consumer.reset_buffer()
  assert consumer._buffer_index == 0


def test_detector_consumer_classify_dummy(data_path):
  # Use high threshold to ensure no random noise triggers detections
  engine = DetectorEngine(data_path, score_threshold=0.8)
  consumer = DetectorConsumer(engine)

  # Send 15600 bytes of silent PCM data
  chunk = b"\x00" * 15600
  sound, score = consumer.process_raw(chunk)

  # Silent input should trigger 'silence' classification
  assert sound == "silence"
  assert score > 0.8
  assert consumer._buffer_index == 0  # Should be reset after processing
