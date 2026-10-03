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
"""Add real-human-speech + real-noise variants and evaluate them.

The first corpus build only mixed the synthetic TTS negatives with noise, which
left the "human speech + real noise" category of the report uncovered. This
script mixes every real human negative (LibriSpeech, African Accented French)
with real ESC-50 environmental noise and with multi-talker babble built from the
same corpora, at 10 dB SNR, then extends the existing production runs at
1e-10 / 1e-15 / 1e-20 with the new samples.

  .venv/bin/python -m benchmarks.wakeword_study.add_real_noisy
"""
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / 'benchmarks'))

from wakeword_study import corpus as corpus  # noqa: E402
from wakeword_study import psprobe  # noqa: E402
from wakeword_study import run_study  # noqa: E402

NOISE_TYPES = ['fan_ac', 'keyboard_office', 'street_traffic', 'babble']
SNR_DB = 10.0
THRESHOLDS = [1e-10, 1e-15, 1e-20]


def build() -> list[dict]:
  """Create the real-human + real-noise samples and extend the manifest."""
  manifest = json.loads(corpus.MANIFEST.read_text(encoding='utf-8'))
  existing = {sample['id'] for sample in manifest['samples']}
  noises = corpus.build_noises()
  _, donors = corpus.build_real_human()
  babble = corpus.build_babble(donors)
  humans = [sample for sample in manifest['samples'] if sample['engine'] == 'human']
  added: list[dict] = []

  for sample in humans:
    if any(sample['id'].endswith(suffix) for suffix in ('-10',)):
      continue

    speech = corpus.decode_raw((corpus.STUDY_DIR / sample['path']).read_bytes())

    for noise_name in NOISE_TYPES:
      noise = babble.get(sample['language']) if noise_name == 'babble' else noises.get(noise_name)

      if noise is None:
        continue

      seed = corpus.zlib.crc32(f'{sample["id"]}|{noise_name}|{SNR_DB}'.encode())
      blended, measured = corpus.mix_at_snr(speech, noise, SNR_DB, seed)
      sample_id = f'realnoise-{sample["id"]}-{noise_name}'

      if sample_id in existing:
        continue

      meta = corpus.write_raw(f'mix/{sample_id}.raw', blended)
      added.append({
        **{key: value for key, value in sample.items() if key not in ('path', 'duration_s', 'bytes', 'sha256')},
        'id': sample_id, 'base_id': sample['id'], 'noise': f'real:{noise_name}', 'snr_db': SNR_DB,
        'noise_measured_snr_db': round(measured, 2),
        'provenance': f'{sample["provenance"]}; mixed with real {noise_name} at {int(SNR_DB)} dB SNR',
        **meta,
      })

  manifest['samples'].extend(added)
  manifest['counts']['negative'] += len(added)
  manifest['counts']['noisy'] += len(added)
  corpus.MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
  print(f'added {len(added)} real-human + real-noise samples', flush=True)

  return added


def evaluate(added: list[dict]) -> None:
  """Extend the existing production runs with the new samples."""
  if not added:
    return

  report = json.loads(run_study.RESULTS.read_text(encoding='utf-8'))

  for threshold in THRESHOLDS:
    for language in ('fr', 'en'):
      key = f'production-A-{language}-{threshold:g}'
      run = next(item for item in report['production_runs'] if item['key'] == key)
      subset = [sample for sample in added if sample['language'] == language]
      started = time.perf_counter()
      setting = psprobe.build_setting(language)
      rows = psprobe.production_pass(setting, 'A_16k_ps16k', threshold, subset)
      run['rows'].extend(rows)
      print(f'{key}: +{len(rows)} rows in {time.perf_counter() - started:.1f}s', flush=True)

  run_study.RESULTS.write_text(json.dumps(report), encoding='utf-8')
  print('results.json updated', flush=True)


def main() -> None:
  """Build the samples and evaluate them."""
  evaluate(build())


if __name__ == '__main__':
  main()
