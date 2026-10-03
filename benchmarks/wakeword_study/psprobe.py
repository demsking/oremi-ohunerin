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
"""PocketSphinx wake-word probe used by the reliability study.

Why this module exists instead of calling WakewordEngine directly:

* PocketSphinx exposes **no keyword score** on the hypothesis. kws_search_hyp()
  writes out_score = 0 and the Python Hypothesis.score is therefore useless.
  The score only survives on the segment returned by ps_seg_iter(), as
  'Segment.prob', which is 'logmath_exp(margin - KWS_MAX)'.
* The detection condition is 'margin >= logmath_log(kws_threshold) >> SENSCR_SHIFT'
  (src/kws_search.c). The margin trajectory does not depend on the threshold;
  the threshold only decides whether a detection is recorded. So one permissive
  pass with reset disabled recovers the maximum margin of the whole utterance,
  from which every threshold outcome -- and the whole sweep -- can be derived.
* A permissive pass also recovers detection latency: the first recorded frame
  whose margin clears the threshold is exactly the frame at which production
  would have reported the wake word.

'to_threshold()' converts a Segment.prob into the equivalent kws_threshold value
so the sweep is expressed in the same units as the constant under test.
"""
import math
import os
import sys
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / 'benchmarks'))

from wakeword_study import corpus as corpus  # noqa: E402

from ohunerin.core.package import APP_NAME  # noqa: E402
from ohunerin.engines.wakeword import is_discriminant_word  # noqa: E402
from ohunerin.models.wakeword import DictionaryEntry  # noqa: E402
from ohunerin.models.wakeword import WakewordSetting  # noqa: E402
from ohunerin.server.http import LANGUAGE_MODEL_PATHS  # noqa: E402
from pocketsphinx import Config  # type: ignore[import-untyped]  # noqa: E402
from pocketsphinx import Decoder  # noqa: E402

#: Log base used by PocketSphinx (sphinxbase logmath default).
LOG_BASE = 1.0001
LN_LOG_BASE = math.log(LOG_BASE)
#: KWS_MAX from src/kws_search.c, in shifted logmath units.
KWS_MAX = 1500
#: SENSCR_SHIFT from sphinxbase (scores are stored divided by 2**10).
SENSCR_SHIFT = 10
#: Very permissive threshold used for the single margin pass. 1e-200 is far
#: below the 1e-30 tail of the reported sweep; it only widens the dynamic range
#: of the recovered margins (the equivalent threshold of a Segment.prob of 0.55
#: is about 1e-200) and cannot change the margin of any stronger detection.
MARGIN_THRESHOLD = 1e-200
#: Thresholds reported in the sweep (production value included explicitly).
SWEEP_THRESHOLDS = [1e-10, 1e-12, 1e-15, 1e-17, 1e-20, 1e-25, 1e-30]
#: Finer ladder used to build score distributions.
LADDER = [10.0 ** (-power) for power in range(6, 46)]
#: 50 ms of audio per process_raw call (fine enough to never miss a detection
#: inside the 10-frame kws_delay window).
CHUNK_SECONDS = 0.05
#: Half a second of silence before and after every clip, as in the regression
#: suite: the wake word must never be lost to a stream that ends inside the
#: PocketSphinx reporting delay.
PAD_SECONDS = 0.5

#: Sample-rate configurations evaluated by the study.
VARIANTS: dict[str, dict] = {
  'A_16k_ps16k': {'rate': 16000, 'ps_samprate': 16000, 'kind': 'native', 'label': '16 kHz source -> PS 16 kHz (production)'},
  'B_16k_down8k_ps8k': {'rate': 8000, 'ps_samprate': 8000, 'kind': 'downsample', 'label': '16 kHz source -> polyphase 8 kHz -> PS 8 kHz'},
  'B2_16k_soxr8k_ps8k': {'rate': 8000, 'ps_samprate': 8000, 'kind': 'soxr', 'label': '16 kHz source -> ffmpeg/soxr 8 kHz -> PS 8 kHz'},
  'D_16k_ps8k_mismatch': {'rate': 16000, 'ps_samprate': 8000, 'kind': 'native', 'label': '16 kHz source -> PS configured 8 kHz (mismatch)'},
  'E_8k_ps16k_mismatch': {'rate': 16000, 'ps_samprate': 16000, 'kind': 'downsample', 'label': '8 kHz source fed to PS 16 kHz (mismatch)'},
}


def build_setting(language: str) -> WakewordSetting:
  """Resolve the wake-word setting for a language exactly like the server does."""
  import json

  raw_config = json.loads((BASE_DIR / 'config.json').read_text(encoding='utf-8'))
  model_rel, dict_rel = LANGUAGE_MODEL_PATHS.get(
    language,
    (f'wakeword-{language}/acoustic-model', f'wakeword-{language}/pronounciation-dictionary.dict'),
  )
  entries = [entry for entry in raw_config['wakewords'] if entry['language'] == language]

  return WakewordSetting(
    model=str(BASE_DIR / 'models' / model_rel),
    dictionary=str(BASE_DIR / 'models' / dict_rel),
    wakewords=[DictionaryEntry(word=entry['word'], phones=entry['phones']) for entry in entries],
    discriminants=[discriminant for entry in entries for discriminant in entry.get('discriminants', [])],
  )


def variant_audio(audio: np.ndarray, variant: str) -> np.ndarray:
  """Apply the variant's sample-rate conversion to a 16 kHz float clip."""
  spec = VARIANTS[variant]

  if spec['kind'] == 'native':
    return audio

  if spec['kind'] == 'downsample':
    return corpus.downsample2(audio)

  if spec['kind'] == 'soxr':
    return corpus.ffmpeg_resample(audio, 16000, 8000)

  raise ValueError(f'unknown variant kind {spec["kind"]!r}')


def prob_to_threshold(prob: float) -> float:
  """Convert a Segment.prob into the equivalent kws_threshold value."""
  if prob <= 0.0:
    return 0.0

  margin = math.log(prob) / LN_LOG_BASE + KWS_MAX
  exponent = margin * (2 ** SENSCR_SHIFT) * LN_LOG_BASE

  if exponent > 700:
    return float('inf')

  return math.exp(exponent)


class StudyDecoder:
  """A PocketSphinx decoder with a runtime-settable kws_threshold."""

  def __init__(self, setting: WakewordSetting, ps_samprate: int, threshold: float) -> None:
    self.setting = setting
    self.ps_samprate = ps_samprate
    self._keyfile = None
    self._decoder = None
    self._build(threshold)

  def _build(self, threshold: float) -> None:
    import tempfile

    directory = tempfile.mkdtemp(prefix='ohunerin-study-')
    self._keyfile = os.path.join(directory, 'keyphrases.list')

    with open(self._keyfile, 'w', encoding='utf-8') as file:
      for entry in self.setting.wakewords + self.setting.discriminants:
        file.write(f'{entry.word}\n')

    config = Config(
      lm=None,
      hmm=self.setting.model,
      dict=self.setting.dictionary,
      kws_threshold=threshold,
      samprate=self.ps_samprate,
    )
    self._decoder = Decoder(config)

    for entry in self.setting.wakewords + self.setting.discriminants:
      for index, phone in enumerate(entry.phones):
        word = entry.word if index == 0 else f'{entry.word}({index + 1})'

        try:
          self._decoder.add_word(word, phone)
        except RuntimeError:
          pass

    self._decoder.add_kws(APP_NAME, self._keyfile)
    self._decoder.activate_search(APP_NAME)

  @property
  def decoder(self) -> Decoder:
    """The underlying native decoder."""
    return self._decoder

  @property
  def config(self) -> Config:
    """The decoder's live PocketSphinx configuration."""
    return self._decoder.config

  def segments(self) -> list:
    """Return the recent detection segments, or an empty list."""
    result = self._decoder.seg()

    return list(result) if result is not None else []

  def reset(self) -> None:
    """Reinitialize the feature extractor and open a fresh utterance."""
    self._decoder.reinit_feat()
    self._decoder.start_utt()

  def close(self) -> None:
    """End the utterance (best effort)."""
    try:
      self._decoder.end_utt()
    except RuntimeError:
      pass


def padded_stream(audio: np.ndarray, rate: int) -> bytes:
  """Return silence + audio + silence as s16le PCM at the given rate."""
  pad = np.zeros(int(PAD_SECONDS * rate))
  stream = np.concatenate([pad, audio, pad])

  return corpus.encode_raw(stream)


def chunk_size(rate: int) -> int:
  """Bytes per process_raw call for a 50 ms frame at the given rate."""
  return int(rate * CHUNK_SECONDS) * 2


def margin_pass(setting: WakewordSetting, variant: str, samples: list[dict], chunk_seconds: float | None = None) -> list[dict]:
  """Recover the maximum wake-word margin of every sample in one permissive pass.

  Detections are not reset, which is safe because the margin trajectory is
  threshold independent; the result is converted to an equivalent threshold so
  the whole 1e-10..1e-30 sweep can be derived from this single pass.
  """
  spec = VARIANTS[variant]
  rate = spec['rate']
  decoder = StudyDecoder(setting, spec['ps_samprate'], MARGIN_THRESHOLD)
  results: list[dict] = []
  wakewords = {entry.word for entry in setting.wakewords}
  bytes_per_chunk = int(rate * (chunk_seconds or CHUNK_SECONDS)) * 2

  for sample in samples:
    audio = corpus.decode_raw((corpus.STUDY_DIR / sample['path']).read_bytes())
    audio = variant_audio(audio, variant)
    stream = padded_stream(audio, rate)
    decoder.reset()
    best_prob = 0.0
    best_frame = None
    margins: dict[str, float] = {}
    frame_probs: dict[int, float] = {}

    for position in range(0, len(stream), bytes_per_chunk):
      decoder.decoder.process_raw(stream[position:position + bytes_per_chunk], False, False)

      for segment in decoder.segments():
        probability = float(segment.prob)
        word = segment.word

        if word in wakewords:
          frame_probs[int(segment.end_frame)] = max(frame_probs.get(int(segment.end_frame), 0.0), probability)

          if probability > best_prob:
            best_prob = probability
            best_frame = int(segment.end_frame)

          margins[word] = max(margins.get(word, 0.0), probability)

    decoder.close()
    results.append({
      'id': sample['id'],
      'language': sample['language'],
      'kind': sample['kind'],
      'label': sample['label'],
      'variant': variant,
      'rate': rate,
      'ps_samprate': spec['ps_samprate'],
      'best_prob': best_prob,
      'margin_threshold': prob_to_threshold(best_prob),
      'best_frame': best_frame,
      'detections': len(frame_probs),
      'frame_probs': {str(k): v for k, v in sorted(frame_probs.items())},
    })

  return results


def production_pass(setting: WakewordSetting, variant: str, threshold: float, samples: list[dict]) -> list[dict]:
  """Reproduce WakewordEngine.process_raw semantics at one threshold.

  Unlike the margin pass this resets the utterance on every detection, exactly
  like the server, and applies the same discriminant filter to the hypothesis
  string. Latency is taken from the detection segment frame.
  """
  spec = VARIANTS[variant]
  rate = spec['rate']
  decoder = StudyDecoder(setting, spec['ps_samprate'], threshold)
  results: list[dict] = []
  bytes_per_chunk = chunk_size(rate)
  pad_bytes = int(PAD_SECONDS * rate) * 2

  for sample in samples:
    audio = corpus.decode_raw((corpus.STUDY_DIR / sample['path']).read_bytes())
    audio = variant_audio(audio, variant)
    stream = padded_stream(audio, rate)
    decoder.reset()
    detection = None
    consumed = 0

    while consumed < len(stream):
      part = stream[consumed:consumed + bytes_per_chunk]
      consumed += len(part)
      decoder.decoder.process_raw(part, False, False)
      hypothesis = decoder.decoder.hyp()

      if hypothesis:
        # WakewordEngine.process_raw ends and restarts the utterance for *every*
        # hypothesis, discriminants included. That reset truncates the margin
        # accumulation of the KWS search, so it is part of the behaviour under
        # test and must not be skipped here.
        is_discriminant = is_discriminant_word(setting, hypothesis.hypstr)

        if not is_discriminant and detection is None:
          segments = decoder.segments()
          end_frame = max((int(segment.end_frame) for segment in segments), default=None)
          detection = {
            'hypstr': hypothesis.hypstr,
            'segments': [segment.word for segment in segments],
            'end_frame': end_frame,
            'stream_bytes': consumed,
            'latency_s': round((end_frame * 0.01) - PAD_SECONDS, 4) if end_frame is not None else None,
          }

        decoder.decoder.end_utt()
        decoder.reset()

    decoder.close()
    results.append({
      'id': sample['id'],
      'language': sample['language'],
      'kind': sample['kind'],
      'label': sample['label'],
      'variant': variant,
      'threshold': threshold,
      'detected': detection is not None,
      'detection': detection,
      'clip_latency_s': round((detection['stream_bytes'] / 2.0 / rate) - PAD_SECONDS, 4) if detection else None,
      'pad_bytes': pad_bytes,
    })

  return results
