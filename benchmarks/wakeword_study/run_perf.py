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
"""Performance and memory cost of the sample-rate variants.

Measures, for the current 16 kHz path and the candidate explicit 8 kHz path:

* decoder construction time and resident memory;
* process_raw cost per 50 ms chunk and the real-time factor;
* the extra CPU cost of the in-process 16 kHz -> 8 kHz polyphase decimation;
* utterance lifecycle cost (reinit_feat + start/end utterance).

Usage: .venv/bin/python -m benchmarks.wakeword_study.run_perf --json
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / 'benchmarks'))

from wakeword_study import corpus as corpus  # noqa: E402
from wakeword_study import psprobe  # noqa: E402


def rss_mb() -> float:
  """Current resident set size in MiB."""
  with open('/proc/self/status', encoding='utf-8') as file:
    for line in file:
      if line.startswith('VmRSS:'):
        return int(line.split()[1]) / 1024.0

  return 0.0


def summarize(samples: list[float]) -> dict:
  """Summarise second-based timings in milliseconds."""
  ordered = sorted(samples)

  return {
    'n': len(ordered),
    'median_ms': round(statistics.median(ordered) * 1e3, 4),
    'p95_ms': round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))] * 1e3, 4),
    'max_ms': round(ordered[-1] * 1e3, 4),
  }


def bench_decoder(language: str, ps_samprate: int) -> dict:
  """Construction cost and RSS of one decoder at a sample rate."""
  setting = psprobe.build_setting(language)
  before = rss_mb()
  started = time.perf_counter()
  decoder = psprobe.StudyDecoder(setting, ps_samprate, 1e-15)
  elapsed = time.perf_counter() - started
  after = rss_mb()
  decoder.close()

  return {'language': language, 'ps_samprate': ps_samprate, 'init_ms': round(elapsed * 1e3, 2), 'rss_mb': round(after - before, 2)}


def bench_process_raw(language: str, ps_samprate: int, rate: int, seconds: float = 6.0) -> dict:
  """Per-chunk process_raw cost while streaming continuous audio."""
  setting = psprobe.build_setting(language)
  decoder = psprobe.StudyDecoder(setting, ps_samprate, 1e-15)
  rng = np.random.default_rng(7)
  audio = rng.normal(0.0, 0.05, int(rate * seconds))
  stream = corpus.encode_raw(audio)
  step = psprobe.chunk_size(rate)
  decoder.reset()
  # Warm up on the first second so the feature extractor and code caches settle.
  offset = 0

  while offset < min(len(stream), rate * 2):
    decoder.decoder.process_raw(stream[offset:offset + step], False, False)
    offset += step

  timings: list[float] = []

  while offset < len(stream):
    started = time.perf_counter()
    decoder.decoder.process_raw(stream[offset:offset + step], False, False)
    timings.append(time.perf_counter() - started)
    offset += step

  decoder.close()
  total = sum(timings)
  audio_seconds = len(timings) * psprobe.CHUNK_SECONDS

  return {
    'language': language, 'ps_samprate': ps_samprate, 'rate': rate,
    'chunk_ms': psprobe.CHUNK_SECONDS * 1e3,
    'chunks': len(timings),
    'per_chunk': summarize(timings),
    'realtime_factor': round(total / audio_seconds, 4),
    'cpu_per_audio_hour_s': round(total / audio_seconds * 3600, 2),
  }


def bench_utterance_cycle(language: str, ps_samprate: int, repeat: int = 300) -> dict:
  """Cost of reinit_feat + start_utt + end_utt, the per-utterance lifecycle."""
  setting = psprobe.build_setting(language)
  decoder = psprobe.StudyDecoder(setting, ps_samprate, 1e-15)
  timings: list[float] = []

  for _ in range(repeat):
    started = time.perf_counter()
    decoder.decoder.reinit_feat()
    decoder.decoder.start_utt()
    decoder.decoder.end_utt()
    timings.append(time.perf_counter() - started)

  decoder.close()

  return {'language': language, 'ps_samprate': ps_samprate, 'cycle': summarize(timings)}


def bench_resample(seconds: float = 60.0) -> dict:
  """CPU cost of the in-process 16 kHz -> 8 kHz decimation."""
  rng = np.random.default_rng(11)
  audio = rng.normal(0.0, 0.1, int(16000 * seconds))
  started = time.perf_counter()
  output = corpus.downsample2(audio)
  elapsed = time.perf_counter() - started

  return {
    'input_seconds': seconds,
    'total_ms': round(elapsed * 1e3, 2),
    'ms_per_audio_second': round(elapsed / seconds * 1e3, 3),
    'cpu_per_audio_hour_s': round(elapsed / seconds * 3600, 3),
    'output_samples': len(output),
  }


def bench_ffmpeg_resample(seconds: float = 5.0) -> dict:
  """Reference cost of ffmpeg/soxr resampling (process spawn included)."""
  rng = np.random.default_rng(12)
  audio = rng.normal(0.0, 0.1, int(16000 * seconds))
  started = time.perf_counter()
  corpus.ffmpeg_resample(audio, 16000, 8000)
  elapsed = time.perf_counter() - started

  return {'input_seconds': seconds, 'total_ms': round(elapsed * 1e3, 2), 'ms_per_audio_second': round(elapsed / seconds * 1e3, 3)}


def main() -> None:
  parser = argparse.ArgumentParser(description='Wake-word study performance benchmarks.')
  parser.add_argument('--json', action='store_true')
  parser.add_argument('--out', default=str(corpus.STUDY_DIR / 'perf.json'))
  args = parser.parse_args()

  report: dict = {'decoders': [], 'process_raw': [], 'utterance_cycle': [], 'resample': {}, 'errors': {}}

  for language, ps_samprate in (('fr', 16000), ('fr', 8000), ('en', 16000)):
    print(f'decoder {language}@{ps_samprate}', flush=True)
    report['decoders'].append(bench_decoder(language, ps_samprate))

  for language, ps_samprate in (('en', 8000),):
    try:
      report['decoders'].append(bench_decoder(language, ps_samprate))
    except RuntimeError as error:
      report['errors'][f'{language}@{ps_samprate}'] = str(error)

  for language, ps_samprate, rate in (('fr', 16000, 16000), ('fr', 8000, 8000), ('en', 16000, 16000)):
    print(f'process_raw {language} ps={ps_samprate} rate={rate}', flush=True)
    report['process_raw'].append(bench_process_raw(language, ps_samprate, rate))

  for language, ps_samprate in (('fr', 16000), ('fr', 8000)):
    report['utterance_cycle'].append(bench_utterance_cycle(language, ps_samprate))

  print('resample', flush=True)
  report['resample']['polyphase'] = bench_resample()
  report['resample']['ffmpeg_soxr'] = bench_ffmpeg_resample()
  Path(args.out).write_text(json.dumps(report, indent=1), encoding='utf-8')

  if args.json:
    print(json.dumps(report, indent=1))
  else:
    for row in report['decoders'] + list(report['errors'].items()):
      print(row)

    for row in report['process_raw']:
      print(f"{row['language']} ps={row['ps_samprate']}: median {row['per_chunk']['median_ms']}ms/chunk, "
            f"RTF {row['realtime_factor']}, {row['cpu_per_audio_hour_s']}s CPU per audio hour")

    print(report['resample'])


if __name__ == '__main__':
  main()
