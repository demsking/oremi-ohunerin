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
"""Run the wake-word reliability study and write a raw results JSON.

Two passes are used (see :mod:`psprobe`):

* a **production pass** -- the exact WakewordEngine semantics at one threshold,
  including the reset on *every* hypothesis. It is the ground truth for the
  threshold sweep, because the KWS margin depends on how often the utterance
  restarts, so detection is NOT monotone in the threshold and cannot be derived
  from a single run.
* a **margin pass** -- one permissive run per sample with the utterance kept
  open, used only for the reset-free side-by-side of the sample-rate variants
  (all variants are treated identically) and for score distributions.

Results are written to `.tmp/wakeword_study/results.json`.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / 'benchmarks'))

from wakeword_study import corpus as corpus  # noqa: E402
from wakeword_study import psprobe  # noqa: E402

RESULTS = corpus.STUDY_DIR / 'results.json'

#: Threshold ladder used by the production passes. Includes every threshold the
#: report tabulates plus finer points for the score distributions.
LADDER = [1e-6, 1e-8, 1e-10, 1e-12, 1e-14, 1e-15, 1e-16, 1e-17, 1e-18, 1e-20, 1e-22, 1e-24, 1e-25, 1e-26, 1e-28, 1e-30, 1e-35]


def select(samples: list[dict], language: str | None = None, kind: str | None = None,
           noise: bool | None = None, engine: str | None = None, label: str | None = None) -> list[dict]:
  """Filter manifest samples for a pass."""
  picked = samples

  if language:
    picked = [s for s in picked if s['language'] == language]

  if kind:
    picked = [s for s in picked if s['kind'] == kind]

  if noise is True:
    picked = [s for s in picked if s['noise']]
  elif noise is False:
    picked = [s for s in picked if not s['noise']]

  if engine:
    picked = [s for s in picked if s['engine'] == engine]

  if label:
    picked = [s for s in picked if s['label'] == label]

  return picked


def margin_job(payload: dict) -> dict:
  """Worker: run one margin pass and return its results."""
  started = time.perf_counter()

  try:
    setting = psprobe.build_setting(payload['language'])
    rows = psprobe.margin_pass(setting, payload['variant'], payload['samples'])
    error = None
  except RuntimeError as failure:
    rows = []
    error = str(failure)

  return {'key': payload['key'], 'language': payload['language'], 'variant': payload['variant'],
          **payload['meta'], 'rows': rows, 'error': error, 'elapsed_s': round(time.perf_counter() - started, 3)}


def production_job(payload: dict) -> dict:
  """Worker: run one production pass and return its results."""
  started = time.perf_counter()

  try:
    setting = psprobe.build_setting(payload['language'])
    rows = psprobe.production_pass(setting, payload['variant'], payload['threshold'], payload['samples'])
    error = None
  except RuntimeError as failure:
    rows = []
    error = str(failure)

  return {'key': payload['key'], 'language': payload['language'], 'variant': payload['variant'],
          'threshold': payload['threshold'], **payload['meta'], 'rows': rows, 'error': error,
          'elapsed_s': round(time.perf_counter() - started, 3)}


def run_jobs(jobs: list[dict], worker, workers: int) -> list[dict]:
  """Execute jobs in a process pool, preserving the job list order."""
  results: list[dict] = []

  with ProcessPoolExecutor(max_workers=workers) as pool:
    for result in pool.map(worker, jobs):
      print(f"  {result['key']}: {len(result['rows'])} rows in {result['elapsed_s']}s", flush=True)
      results.append(result)

  return results


def build_jobs(manifest: dict) -> tuple[list[dict], list[dict]]:
  """Build the margin and production job lists."""
  samples = manifest['samples']
  margin_jobs: list[dict] = []
  production_jobs: list[dict] = []

  # 1. Production ladder, variant A (production), every sample.
  for language in ('fr', 'en'):
    subset = select(samples, language=language)

    for threshold in LADDER:
      production_jobs.append({
        'key': f'production-A-{language}-{threshold:g}', 'language': language, 'variant': 'A_16k_ps16k',
        'threshold': threshold, 'samples': subset, 'meta': {'scope': 'all', 'group': 'sweep'},
      })

  # 2. French sample-rate variants, same ladder, over the whole French corpus.
  for variant in ('B_16k_down8k_ps8k', 'B2_16k_soxr8k_ps8k'):
    subset = select(samples, language='fr')

    for threshold in LADDER:
      production_jobs.append({
        'key': f'production-{variant.split("_")[0]}-fr-{threshold:g}', 'language': 'fr', 'variant': variant,
        'threshold': threshold, 'samples': subset, 'meta': {'scope': 'all', 'group': 'sample_rate'},
      })

  # 3. Reset-free margin passes used only to compare variants side by side.
  for language in ('fr', 'en'):
    clean = select(samples, language=language, noise=False)
    noisy = select(samples, language=language, noise=True)

    for variant in ('A_16k_ps16k', 'B_16k_down8k_ps8k', 'B2_16k_soxr8k_ps8k'):
      margin_jobs.append({
        'key': f'margin-{variant.split("_")[0]}-{language}-clean', 'language': language, 'variant': variant,
        'samples': clean, 'meta': {'scope': 'clean', 'group': 'sample_rate'},
      })

      if language == 'fr':
        margin_jobs.append({
          'key': f'margin-{variant.split("_")[0]}-fr-noisy', 'language': 'fr', 'variant': variant,
          'samples': noisy, 'meta': {'scope': 'noisy', 'group': 'sample_rate'},
        })

  # Deliberate sample-rate mismatches: these are the controls that show whether
  # PocketSphinx resamples anything on its own (it does not).
  fr_clean = select(samples, language='fr', noise=False)
  margin_jobs.append({
    'key': 'margin-D-fr-clean', 'language': 'fr', 'variant': 'D_16k_ps8k_mismatch',
    'samples': fr_clean, 'meta': {'scope': 'clean', 'group': 'mismatch'},
  })
  margin_jobs.append({
    'key': 'margin-E-fr-clean', 'language': 'fr', 'variant': 'E_8k_ps16k_mismatch',
    'samples': fr_clean, 'meta': {'scope': 'clean', 'group': 'mismatch'},
  })

  return margin_jobs, production_jobs


def environment_fingerprint() -> dict:
  """Capture the versions and constants the results depend on."""
  import numpy

  import pocketsphinx

  return {
    'python': platform.python_version(),
    'platform': platform.platform(),
    'numpy': numpy.__version__,
    'pocketsphinx_package': getattr(pocketsphinx, '__file__', 'unknown'),
    'pocketsphinx_version': importlib.metadata.version('pocketsphinx'),
    'cpu_count': os.cpu_count(),
    'chunk_seconds': psprobe.CHUNK_SECONDS,
    'pad_seconds': psprobe.PAD_SECONDS,
    'margin_threshold': psprobe.MARGIN_THRESHOLD,
    'sweep_thresholds': psprobe.SWEEP_THRESHOLDS,
    'ladder': LADDER,
    'variants': {key: value for key, value in psprobe.VARIANTS.items()},
  }


def main() -> None:
  parser = argparse.ArgumentParser(description='Run the wake-word reliability study.')
  parser.add_argument('--workers', type=int, default=min(12, os.cpu_count() or 4))
  parser.add_argument('--only', choices=['margins', 'production', 'all'], default='all')
  parser.add_argument('--out', default=str(RESULTS))
  args = parser.parse_args()

  manifest = json.loads(corpus.MANIFEST.read_text(encoding='utf-8'))
  print(f"manifest: {manifest['counts']}", flush=True)
  margin_jobs, production_jobs = build_jobs(manifest)
  report: dict = {
    'manifest_counts': manifest['counts'],
    'manifest_path': str(corpus.MANIFEST),
    'environment': environment_fingerprint(),
    'margin_runs': [],
    'production_runs': [],
  }

  started = time.perf_counter()

  if args.only in ('margins', 'all'):
    print(f'running {len(margin_jobs)} margin jobs', flush=True)
    report['margin_runs'] = run_jobs(margin_jobs, margin_job, args.workers)

  if args.only in ('production', 'all'):
    print(f'running {len(production_jobs)} production jobs', flush=True)
    report['production_runs'] = run_jobs(production_jobs, production_job, args.workers)

  report['elapsed_s'] = round(time.perf_counter() - started, 1)
  Path(args.out).write_text(json.dumps(report), encoding='utf-8')
  digest = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()[:16]
  print(f'wrote {args.out} ({digest}) in {report["elapsed_s"]}s', flush=True)


if __name__ == '__main__':
  main()
