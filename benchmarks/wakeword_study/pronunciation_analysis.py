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
"""Tables for the controlled pronunciation benchmark.

Reads pronunciation_results.json (see pronunciation.py) and prints the comparison
between keyphrase/dictionary variants, broken down by spoken pronunciation and by
TTS voice so a single-voice win cannot be mistaken for a general improvement.
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wakeword_study import corpus as corpus
from wakeword_study import pronunciation as pronunciation


def load(path: Path) -> dict:
  """Load the pronunciation results file."""
  return json.loads(path.read_text(encoding='utf-8'))


def job(blob: dict, variant: str, threshold: float) -> list[dict]:
  """Rows of one variant/threshold job."""
  for entry in blob['jobs']:
    if entry['variant'] == variant and abs(entry['threshold'] - threshold) < 1e-300:
      return entry['rows']

  raise KeyError(f'{variant}@{threshold}')


def is_positive(row: dict) -> bool:
  """Primary wake-word positive."""
  return row['kind'] == 'positive'


def is_negative(row: dict) -> bool:
  """Must not fire."""
  return row['kind'] == 'negative'


def quantile(values: list[float], q: float) -> float | None:
  """Nearest-rank quantile."""
  if not values:
    return None

  ordered = sorted(values)

  return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def overall_table(blob: dict, variants: list[str], thresholds: list[float]) -> str:
  """TP/FP per variant and threshold."""
  lines = ['| Variant | Threshold | TP | n | TPR | FP | FPR | latency median / p90 (s) |',
           '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']

  for variant in variants:
    for threshold in thresholds:
      rows = job(blob, variant, threshold)
      positives = [row for row in rows if is_positive(row)]
      negatives = [row for row in rows if is_negative(row)]
      tp = sum(1 for row in positives if row['detected'])
      fp = sum(1 for row in negatives if row['detected'])
      latency = [row['latency_s'] for row in positives if row['detected'] and row['latency_s'] is not None]
      median = quantile(latency, 0.5)
      p90 = quantile(latency, 0.9)
      latency_text = f'{median:.2f} / {p90:.2f}' if median is not None else 'n/a'
      lines.append(f'| {variant} | 1e{round(math.log10(threshold))} | {tp} | {len(positives)} | '
                   f'{tp / max(len(positives), 1):.3f} | {fp} | {fp / max(len(negatives), 1):.3f} | {latency_text} |')

  return chr(10).join(lines)


def by_pronunciation_table(blob: dict, variants: list[str], threshold: float) -> str:
  """Detection rate per spoken pronunciation (controlled TTS atoms) and variant."""
  rows = job(blob, variants[0], threshold)
  names = [name for name in pronunciation.PRONUNCIATIONS if any(row['pronunciation'] == name for row in rows)]
  lines = ['| Spoken pronunciation | IPA | ' + ' | '.join(variants) + ' |',
           '| --- | --- | ' + ' | '.join('---:' for _ in variants) + ' |']

  for name in names:
    ipa = pronunciation.PRONUNCIATIONS[name][1]
    cells = []

    for variant in variants:
      members = [row for row in job(blob, variant, threshold) if row['pronunciation'] == name]
      hits = sum(1 for row in members if row['detected'])
      cells.append(f'{hits}/{len(members)}')

    lines.append(f'| {name} | {ipa} | ' + ' | '.join(cells) + ' |')

  return chr(10).join(lines)


def by_voice_table(blob: dict, variants: list[str], threshold: float) -> str:
  """Detection rate per TTS voice for each variant (generalisation check)."""
  names = sorted({row['voice'].split('@')[0] for row in job(blob, variants[0], threshold)
                  if row['pronunciation']})
  lines = ['| Voice | ' + ' | '.join(variants) + ' |', '| --- | ' + ' | '.join('---:' for _ in variants) + ' |']

  for voice in names:
    cells = []

    for variant in variants:
      members = [row for row in job(blob, variant, threshold)
                 if row['pronunciation'] and row['voice'].split('@')[0] == voice]
      hits = sum(1 for row in members if row['detected'])
      cells.append(f'{hits}/{len(members)}')

    lines.append(f'| {voice} | ' + ' | '.join(cells) + ' |')

  return chr(10).join(lines)


def false_positive_table(blob: dict, variants: list[str], threshold: float, meta: dict[str, dict]) -> str:
  """False positives grouped by negative kind."""
  lines = ['| Negative set | n | ' + ' | '.join(variants) + ' |',
           '| --- | ---: | ' + ' | '.join('---:' for _ in variants) + ' |']
  groups = ['near_homophone', 'similar_name', 'partial', 'unrelated',
            'real_human_unrelated', 'real_human_near_homophone']

  for group in groups:
    members = [row for row in job(blob, variants[0], threshold)
               if is_negative(row) and meta.get(row['id'], {}).get('label') == group]

    if not members:
      continue

    cells = []

    for variant in variants:
      hits = {row['id']: row['detected'] for row in job(blob, variant, threshold)}
      cells.append(str(sum(1 for row in members if hits.get(row['id']))))

    lines.append(f'| {group} | {len(members)} | ' + ' | '.join(cells) + ' |')

  return chr(10).join(lines)


def main() -> None:
  parser = argparse.ArgumentParser(description='Analyse the pronunciation benchmark.')
  parser.add_argument('--results', default=str(corpus.STUDY_DIR / 'pronunciation_results.json'))
  parser.add_argument('--section', default='all', choices=['all', 'overall', 'pronunciation', 'voice', 'fp'])
  args = parser.parse_args()

  blob = load(Path(args.results))
  variants = list(pronunciation.KWS_VARIANTS)
  thresholds = sorted({entry['threshold'] for entry in blob['jobs']})
  meta = {sample['id']: sample for sample in json.loads(corpus.MANIFEST.read_text(encoding='utf-8'))['samples']}
  output: list[str] = []

  if args.section in ('all', 'overall'):
    output.append('## Overall (all samples: controlled pronunciations + existing corpus)')
    output.append(overall_table(blob, variants, thresholds))

  if args.section in ('all', 'pronunciation'):
    output.append('\\n## Detection rate by spoken pronunciation (8 pronunciations x 9 voices x 2 speeds = 18 each)')
    output.append(by_pronunciation_table(blob, variants, thresholds[0]))

  if args.section in ('all', 'voice'):
    output.append('\\n## Detection rate by TTS voice (generalisation check)')
    output.append(by_voice_table(blob, variants, thresholds[0]))

  if args.section in ('all', 'fp'):
    output.append('\\n## False positives by negative set')
    output.append(false_positive_table(blob, variants, thresholds[0], meta))

  text = chr(10).join(output)
  (corpus.STUDY_DIR / 'pronunciation_analysis.md').write_text(text, encoding='utf-8')
  print(text)


if __name__ == '__main__':
  main()
