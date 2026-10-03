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
"""Chunk-size and kws_delay behaviour of the production streaming path.

The reliability study reproduced 1,223/1,224 production verdicts at 50 ms chunks;
one French positive flipped. This module measures that systematically: identical PCM
is pushed through a decoder that mirrors WakewordEngine exactly, varying only the
chunk size (10 ms to 500 ms) and kws_delay (0 to 40 frames).

It answers whether the mismatch is random or a systematic frame-alignment effect,
and whether kws_delay changes search behaviour or only the reporting delay.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wakeword_study import corpus as corpus
from wakeword_study import psprobe

from ohunerin.core.package import APP_NAME
from ohunerin.engines.wakeword import KWS_THRESHOLD
from ohunerin.engines.wakeword import is_discriminant_word
from pocketsphinx import Config  # type: ignore[import-untyped]
from pocketsphinx import Decoder

CHUNK_BYTES = [320, 640, 800, 1600, 3200, 4000, 8000, 16000]
DELAYS = [0, 5, 10, 20, 40]
PAD_SECONDS = 0.5


class ProductionMirror:
  """Byte-for-byte mirror of WakewordEngine with configurable chunking and delay."""

  def __init__(self, language: str, kws_delay: int = 10) -> None:
    self.setting = psprobe.build_setting(language)
    directory = tempfile.mkdtemp(prefix='ohunerin-stream-')
    self.keyfile = os.path.join(directory, 'keyphrases.list')

    with open(self.keyfile, 'w', encoding='utf-8') as file:
      for entry in self.setting.wakewords + self.setting.discriminants:
        file.write(f'{entry.word}\n')

    config = Config(
      lm=None,
      hmm=self.setting.model,
      dict=self.setting.dictionary,
      kws_threshold=KWS_THRESHOLD,
      kws_delay=kws_delay,
    )
    self.decoder = Decoder(config)

    for entry in self.setting.wakewords + self.setting.discriminants:
      for index, phone in enumerate(entry.phones):
        word = entry.word if index == 0 else f'{entry.word}({index + 1})'

        try:
          self.decoder.add_word(word, phone)
        except RuntimeError:
          pass

    self.decoder.add_kws(APP_NAME, self.keyfile)
    self.decoder.activate_search(APP_NAME)
    self.kws_delay = kws_delay

  def begin(self) -> None:
    """reinit_feat + start_utt, exactly like WakewordEngine._begin_utterance."""
    self.decoder.reinit_feat()
    self.decoder.start_utt()

  def end(self) -> None:
    """End the current utterance."""
    try:
      self.decoder.end_utt()
    except RuntimeError:
      pass

  def process(self, chunk: bytes) -> tuple[str | None, int | None]:
    """One process_raw call with production semantics; returns (word, end_frame)."""
    self.decoder.process_raw(chunk, False, False)
    hypothesis = self.decoder.hyp()

    if not hypothesis:
      return None, None

    is_discriminant = is_discriminant_word(self.setting, hypothesis.hypstr)
    segments = self.decoder.seg()
    segments = list(segments) if segments is not None else []
    end_frame = max((int(segment.end_frame) for segment in segments), default=None)
    self.decoder.end_utt()
    self.begin()

    if is_discriminant:
      return None, end_frame

    return hypothesis.hypstr, end_frame


def run_config(payload: dict) -> dict:
  """Worker: stream every sample through one (chunk size, kws_delay) configuration."""
  started = time.perf_counter()
  language = payload['language']
  engine = ProductionMirror(language, payload['kws_delay'])
  rate = 16000
  chunk_bytes = payload['chunk_bytes']
  rows = []

  for sample in payload['samples']:
    import numpy as np

    audio = corpus.decode_raw((corpus.STUDY_DIR / sample['path']).read_bytes())
    pad = np.zeros(int(PAD_SECONDS * rate))
    stream = corpus.encode_raw(np.concatenate([pad, audio, pad]))
    engine.begin()
    detection = None
    consumed = 0

    while consumed < len(stream):
      part = stream[consumed:consumed + chunk_bytes]
      consumed += len(part)
      word, end_frame = engine.process(part)

      if word and detection is None:
        detection = {
          'word': word, 'end_frame': end_frame,
          'stream_bytes': consumed,
          'latency_s': round(end_frame * 0.01 - PAD_SECONDS, 3) if end_frame is not None else None,
        }

    engine.end()
    rows.append({
      'id': sample['id'], 'kind': sample['kind'], 'label': sample['label'],
      'detected': detection is not None, 'detection': detection,
      'latency_s': detection['latency_s'] if detection and detection['latency_s'] is not None else None,
    })

  return {
    'key': f"{language}-{chunk_bytes}-{payload['kws_delay']}",
    'language': language, 'chunk_bytes': chunk_bytes, 'kws_delay': payload['kws_delay'],
    'chunk_ms': round(chunk_bytes / 2 / rate * 1000, 1),
    'rows': rows, 'elapsed_s': round(time.perf_counter() - started, 3),
  }


def main() -> None:
  parser = argparse.ArgumentParser(description='Chunk size and kws_delay benchmark.')
  parser.add_argument('--workers', type=int, default=min(10, os.cpu_count() or 4))
  parser.add_argument('--out', default=str(corpus.STUDY_DIR / 'streaming_results.json'))
  args = parser.parse_args()

  study = json.loads(corpus.MANIFEST.read_text(encoding='utf-8'))['samples']
  pron_manifest = corpus.STUDY_DIR / 'pronunciation_manifest.json'
  samples = []

  if pron_manifest.exists():
    samples.extend(json.loads(pron_manifest.read_text(encoding='utf-8'))['samples'])

  for language in ('fr', 'en'):
    clean_positives = [s for s in study if s['language'] == language and s['kind'] == 'positive' and not s['noise']]
    negatives = [s for s in study if s['language'] == language and s['kind'] == 'negative'
                 and (s['engine'] == 'human' or not s['noise'])]
    samples.extend(clean_positives)
    samples.extend(negatives)

  jobs = []

  for language in ('fr', 'en'):
    subset = [s for s in samples if s['language'] == language]

    for chunk_bytes in CHUNK_BYTES:
      jobs.append({'language': language, 'chunk_bytes': chunk_bytes, 'kws_delay': 10, 'samples': subset})

    for delay in DELAYS:
      jobs.append({'language': language, 'chunk_bytes': 8000, 'kws_delay': delay, 'samples': subset})

  print(f'running {len(jobs)} streaming jobs', flush=True)
  started = time.perf_counter()
  results = []

  with ProcessPoolExecutor(max_workers=args.workers) as pool:
    for result in pool.map(run_config, jobs):
      print(f"  {result['key']}: {len(result['rows'])} rows in {result['elapsed_s']}s", flush=True)
      results.append(result)

  Path(args.out).write_text(json.dumps({'jobs': results}), encoding='utf-8')
  print(f'wrote {args.out} in {time.perf_counter() - started:.0f}s')


if __name__ == '__main__':
  main()
