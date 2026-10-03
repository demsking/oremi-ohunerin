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
"""Production-path wake-word benchmark, used for the French pronunciation change.

Runs *both* paths over the same PCM and reports them separately per language:

* production -- the real ohunerin.engines.wakeword.WakewordEngine, exactly what the
  WebSocket server uses, driven with the reference client block size (8000 bytes);
* probe -- psprobe.production_pass(), the independently written reproduction of the
  same semantics used by the reliability and pronunciation studies.

Sample sets are the ones the pronunciation study reported on: French intended
positives (276 corpus positives + 36 controlled clips) against 464 French negatives,
and 306 English positives against 530 English negatives, at kws_threshold=1e-15.

  .venv/bin/python -m benchmarks.wakeword_study.production_check --label before
"""
import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wakeword_study import corpus as corpus
from wakeword_study import psprobe

from ohunerin.engines.wakeword import WakewordEngine

CHUNK_BYTES = 8000
PAD_SECONDS = 0.5


def sample_sets() -> dict[str, dict[str, list[dict]]]:
  """Return the positive/negative sample lists per language, as used by the study."""
  study = json.loads(corpus.MANIFEST.read_text(encoding='utf-8'))['samples']
  prons = json.loads((corpus.STUDY_DIR / 'pronunciation_manifest.json').read_text(encoding='utf-8'))['samples']
  sets: dict[str, dict[str, list[dict]]] = {}

  for language in ('fr', 'en'):
    positives = [s for s in study if s['language'] == language and s['kind'] == 'positive']
    negatives = [s for s in study if s['language'] == language and s['kind'] == 'negative']

    if language == 'fr':
      positives = positives + [s for s in prons if s['pronunciation'] in ('o_re', 'openo_re')]

    sets[language] = {'positive': positives, 'negative': negatives}

  return sets


def stream(sample: dict) -> bytes:
  """Silence + clip + silence as s16le PCM, like the regression suite."""
  audio = corpus.decode_raw((corpus.STUDY_DIR / sample['path']).read_bytes())
  pad = np.zeros(int(PAD_SECONDS * 16000))

  return corpus.encode_raw(np.concatenate([pad, audio, pad]))


def run_production(language: str, samples: list[dict]) -> list[dict]:
  """Verdicts from the real WakewordEngine, one decoder for the whole set."""
  engine = WakewordEngine(psprobe.build_setting(language))
  rows = []

  for sample in samples:
    data = stream(sample)
    engine.start_utt()
    detection = None
    consumed = 0

    while consumed < len(data):
      part = data[consumed:consumed + CHUNK_BYTES]
      consumed += len(part)
      word, _score = engine.process_raw(part)

      if word:
        detection = word

    engine.end_utt()
    rows.append({'id': sample['id'], 'detected': detection is not None, 'hypothesis': detection})

  return rows


def run_probe(language: str, samples: list[dict]) -> list[dict]:
  """Verdicts from the independent production_pass() reproduction."""
  rows = psprobe.production_pass(psprobe.build_setting(language), 'A_16k_ps16k', 1e-15, samples)

  return [
    {
      'id': row['id'],
      'detected': row['detected'],
      'hypothesis': row['detection']['hypstr'] if row['detection'] else None,
      'latency_s': row['clip_latency_s'],
    }
    for row in rows
  ]


def metrics(rows: list[dict], sets: dict[str, list[dict]]) -> dict:
  """TP/FN/TPR/FP/FPR/Youden J for one path."""
  positives = {s['id'] for s in sets['positive']}
  negatives = {s['id'] for s in sets['negative']}
  verdict = {row['id']: row['detected'] for row in rows}
  tp = sum(1 for sid in positives if verdict.get(sid))
  fp = sum(1 for sid in negatives if verdict.get(sid))
  tpr = tp / len(positives)
  fpr = fp / len(negatives)
  latencies = sorted(
    row['latency_s']
    for row in rows
    if row['id'] in positives and row['detected'] and row.get('latency_s') is not None
  )
  median = latencies[len(latencies) // 2] if latencies else None

  return {
    'positives': len(positives), 'negatives': len(negatives),
    'tp': tp, 'fn': len(positives) - tp, 'tpr': round(tpr, 4),
    'fp': fp, 'fpr': round(fpr, 4), 'j': round(tpr - fpr, 4),
    'latency_median_s': median,
  }


def job(payload: dict) -> dict:
  """Worker: run one path for one language."""
  started = time.perf_counter()
  sets = sample_sets()[payload['language']]
  samples = sets['positive'] + sets['negative']
  rows = run_production(payload['language'], samples) if payload['path'] == 'production' \
    else run_probe(payload['language'], samples)

  return {'language': payload['language'], 'path': payload['path'], 'rows': rows,
          'metrics': metrics(rows, sets), 'elapsed_s': round(time.perf_counter() - started, 1)}


def main() -> None:
  parser = argparse.ArgumentParser(description='Production-path wake-word benchmark.')
  parser.add_argument('--label', default='run', help='label stored with the results')
  parser.add_argument('--workers', type=int, default=4)
  parser.add_argument('--out', default=None)
  args = parser.parse_args()
  out = Path(args.out) if args.out else corpus.STUDY_DIR / f'production_check_{args.label}.json'
  jobs = [{'language': language, 'path': path} for language in ('fr', 'en') for path in ('production', 'probe')]
  print(f'running {len(jobs)} jobs', flush=True)
  started = time.perf_counter()
  results = []

  with ProcessPoolExecutor(max_workers=args.workers) as pool:
    for result in pool.map(job, jobs):
      print(f"  {result['language']}/{result['path']}: {result['metrics']} in {result['elapsed_s']}s", flush=True)
      results.append(result)

  out.write_text(json.dumps({'label': args.label, 'chunk_bytes': CHUNK_BYTES, 'jobs': results}, indent=1))
  print(f'wrote {out} in {time.perf_counter() - started:.0f}s')


if __name__ == '__main__':
  main()
