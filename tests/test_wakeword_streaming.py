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
from pathlib import Path

import pytest

from ohunerin.engines.wakeword import WakewordEngine
from ohunerin.models.wakeword import DictionaryEntry
from ohunerin.models.wakeword import WakewordSetting

# These tests load the real CMU Sphinx models and the fixed PCM recordings in
# tests/fixtures (see tests/fixtures/README.md). They need no network access.

BASE_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"

#: 0.5 s of silence: continuous audio before and after the wake word, so a
#: detection is never lost to a stream that stops inside the PocketSphinx
#: reporting delay.
SILENCE = b"\x00" * 16000

#: WebSocket frame sizes, smallest to largest: below one PocketSphinx frame,
#: one and two frames, the client block size (8 000 B = 250 ms), one second, and
#: one frame carrying the whole recording. Every one of them splits the wake word
#: at a different point, and none of them may lose the detection.
CHUNK_SIZES = [320, 640, 1600, 3200, 8000, 16000, 64000]


@pytest.fixture
def logger():
  return logging.getLogger("test_wakeword_streaming")


@pytest.fixture
def en_setting() -> WakewordSetting:
  return WakewordSetting(
    model=os.path.join(str(BASE_DIR), "models/wakeword-en/acoustic-model"),
    dictionary=os.path.join(str(BASE_DIR), "models/wakeword-en/pronounciation-dictionary.dict"),
    wakewords=[DictionaryEntry(word="oremi", phones=["OW R EH M IY", "OW R EY M IY", "AO R EH M IY", "AO R EY M IY"])],
    discriminants=[DictionaryEntry(word="remi", phones=["R EH M IY", "R EY M IY"])],
  )


@pytest.fixture
def fr_setting() -> WakewordSetting:
  return WakewordSetting(
    model=os.path.join(str(BASE_DIR), "models/wakeword-fr/cmusphinx-fr-ptm-8khz-5.2"),
    dictionary=os.path.join(str(BASE_DIR), "models/wakeword-fr/pronounciation-dictionary.dict"),
    wakewords=[DictionaryEntry(word="oremi", phones=["oo rr ei mm ii", "oo rr ai mm ii"])],
    discriminants=[DictionaryEntry(word="remi", phones=["rr ei mm ii", "rr ai mm ii"])],
  )


def load_fixture(name: str) -> bytes:
  return (FIXTURES_DIR / name).read_bytes()


def detect(engine: WakewordEngine, audio: bytes, chunk_size: int) -> list[str]:
  """Feed one recording through an engine in fixed-size chunks.

  Args:
    engine: The wake-word decoder reused for this utterance.
    audio: Raw 16 kHz mono signed int16 PCM.
    chunk_size: Bytes per process_raw call, i.e. per WebSocket frame.

  Returns:
    list[str]: The non-discriminant hypotheses reported while streaming.
  """
  engine.start_utt()
  stream = SILENCE + audio + SILENCE
  detections: list[str] = []
  position = 0

  while position < len(stream):
    part = stream[position:position + chunk_size]
    position += len(part)
    word, _score = engine.process_raw(part)

    if word:
      detections.append(word)

  engine.end_utt()
  return detections


def test_english_wake_word_is_detected_for_every_frame_size(en_setting):
  engine = WakewordEngine(en_setting)
  audio = load_fixture("wakeword-en-oremi-16k.raw")

  for chunk_size in CHUNK_SIZES:
    detections = detect(engine, audio, chunk_size)
    assert any("oremi" in word for word in detections), f"wake word lost with {chunk_size}-byte frames"

  del engine


def test_french_wake_word_is_detected_for_every_frame_size(fr_setting):
  engine = WakewordEngine(fr_setting)
  audio = load_fixture("wakeword-fr-oremi-16k.raw")

  for chunk_size in CHUNK_SIZES:
    detections = detect(engine, audio, chunk_size)
    assert "oremi" in detections, f"wake word lost with {chunk_size}-byte frames"

  del engine


def test_wake_word_is_detected_when_split_across_two_frames(en_setting):
  """Feed the recording over two frames so the wake word straddles the boundary."""
  engine = WakewordEngine(en_setting)
  audio = load_fixture("wakeword-en-oremi-16k.raw")
  half = len(audio) // 2

  detections = detect(engine, audio, half)

  assert any("oremi" in word for word in detections)
  del engine


def test_decoder_keeps_detecting_after_many_utterances(fr_setting):
  """Regression: the feature extractor used to accumulate CMN statistics.

  A reused decoder went permanently deaf after a handful of detections. The
  French model was the reproducible case (5/30 before the fix, 100/100 after).
  """
  engine = WakewordEngine(fr_setting)
  audio = load_fixture("wakeword-fr-oremi-16k.raw")
  misses = [index for index in range(20) if not detect(engine, audio, 8000)]

  assert misses == [], f"decoder stopped detecting on utterances {misses}"
  del engine


def test_silence_never_triggers_the_wake_word(fr_setting):
  engine = WakewordEngine(fr_setting)

  assert detect(engine, b"", 8000) == []
  del engine
