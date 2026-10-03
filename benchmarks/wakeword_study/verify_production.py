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
"""Validate the study harness against the unmodified production code path.

Every claim in the study rests on psprobe.production_pass() reproducing
WakewordEngine.process_raw(). This script feeds the same PCM through the real
class -- the one the WebSocket server uses -- and compares the fired/not-fired
verdict sample by sample at 1e-15.

  .venv/bin/python -m benchmarks.wakeword_study.verify_production
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / 'benchmarks'))

from wakeword_study import corpus as corpus  # noqa: E402
from wakeword_study import psprobe  # noqa: E402
from ohunerin.engines.wakeword import WakewordEngine  # noqa: E402

CHUNK_BYTES = 8000
THRESHOLD_KEY = 'production-A-{language}-1e-15'


def real_engine_verdict(language: str, audio: bytes) -> bool:
  """Run the production WakewordEngine exactly like the server does."""
  engine = WakewordEngine(psprobe.build_setting(language))
  stream = b'\x00' * 16000 + audio + b'\x00' * 16000
  engine.start_utt()
  fired = False

  for position in range(0, len(stream), CHUNK_BYTES):
    word, _score = engine.process_raw(stream[position:position + CHUNK_BYTES])

    if word:
      fired = True
      break

  engine.end_utt()

  return fired


def main() -> None:
  """Compare the real engine with the recorded production-pass verdicts."""
  manifest = json.loads(corpus.MANIFEST.read_text(encoding='utf-8'))
  report = json.loads((corpus.STUDY_DIR / 'results.json').read_text(encoding='utf-8'))
  recorded: dict[str, dict[str, bool]] = {}

  for run in report['production_runs']:
    if run['key'].endswith('-1e-15') and run['key'].startswith('production-A-'):
      language = run['key'].split('-')[2]
      recorded[language] = {row['id']: row['detected'] for row in run['rows']}

  mismatches = []
  checked = 0

  for sample in manifest['samples']:
    language = sample['language']

    if sample['id'] not in recorded.get(language, {}):
      continue

    audio = (corpus.STUDY_DIR / sample['path']).read_bytes()
    actual = real_engine_verdict(language, audio)
    expected = recorded[language][sample['id']]
    checked += 1

    if actual != expected:
      mismatches.append((sample['id'], expected, actual, sample['text'][:40]))

  print(f'checked {checked} samples against WakewordEngine at 1e-15, mismatches: {len(mismatches)}')

  for mismatch in mismatches[:20]:
    print('  MISMATCH', mismatch)


if __name__ == '__main__':
  main()
