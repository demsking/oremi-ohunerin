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
"""Turn the raw study results into the tables used by the report.

Ground truth is the *production* pass: it reproduces WakewordEngine.process_raw
byte for byte, including the utterance reset on every hypothesis. The KWS
margin depends on how often the utterance restarts, so detection is not monotone
in the threshold and each threshold is measured independently.
"""
import argparse
import json
import math
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / 'benchmarks'))

from wakeword_study import corpus as corpus  # noqa: E402
from wakeword_study import psprobe  # noqa: E402

SWEEP = psprobe.SWEEP_THRESHOLDS


def load(path: Path) -> dict:
  """Load the raw results file."""
  return json.loads(path.read_text(encoding='utf-8'))


def metadata() -> dict[str, dict]:
  """Map sample id to its manifest metadata."""
  manifest = json.loads(corpus.MANIFEST.read_text(encoding='utf-8'))

  return {sample['id']: sample for sample in manifest['samples']}


def production_run(report: dict, key: str) -> list[dict]:
  """Rows of one production run."""
  for run in report['production_runs']:
    if run['key'] == key:
      return run['rows']

  raise KeyError(key)


def margin_run(report: dict, key: str) -> list[dict]:
  """Rows of one margin run, or an empty list when the run failed."""
  for run in report['margin_runs']:
    if run['key'] == key:
      return run['rows']

  return []


def errors(report: dict) -> dict:
  """Runs that failed, keyed by run key."""
  return {run['key']: run['error'] for run in report['margin_runs'] + report['production_runs'] if run.get('error')}


def fired(report: dict, variant: str, language: str, threshold: float) -> dict[str, bool]:
  """Map sample id to detection for one (variant, language, threshold)."""
  key = f'production-{variant.split("_")[0]}-{language}-{threshold:g}'

  return {row['id']: row['detected'] for row in production_run(report, key)}


def present(report: dict, variant: str, language: str, threshold: float) -> set[str]:
  """Sample ids actually measured by one production run."""
  key = f'production-{variant.split("_")[0]}-{language}-{threshold:g}'

  return {row['id'] for row in production_run(report, key)}


def latencies(report: dict, variant: str, language: str, threshold: float, only_ids: set[str]) -> list[float]:
  """Detection latencies for the samples that fired."""
  key = f'production-{variant.split("_")[0]}-{language}-{threshold:g}'
  values = []

  for row in production_run(report, key):
    if row['id'] in only_ids and row['detected'] and row['clip_latency_s'] is not None:
      values.append(row['clip_latency_s'])

  return values


def quantile(values: list[float], q: float) -> float | None:
  """Simple nearest-rank quantile."""
  if not values:
    return None

  ordered = sorted(values)

  return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def ids_for(meta: dict[str, dict], language: str, predicate) -> set[str]:
  """Sample ids matching a predicate over manifest metadata."""
  return {sid for sid, sample in meta.items() if sample['language'] == language and predicate(sample)}


def is_primary_positive(sample: dict) -> bool:
  """A wake-word utterance in the intended pronunciation (not the literal spelling)."""
  return sample['kind'] == 'positive' and sample['label'] == 'wakeword'


def is_literal_positive(sample: dict) -> bool:
  """A wake-word utterance in the literal brand spelling."""
  return sample['kind'] == 'positive' and sample['label'] == 'wakeword_literal'


def is_negative(sample: dict) -> bool:
  """Anything that must not trigger."""
  return sample['kind'] == 'negative'


def sweep_table(report: dict, meta: dict[str, dict], language: str, variant: str = 'A_16k_ps16k') -> str:
  """Threshold sweep from the production passes."""
  positives = ids_for(meta, language, is_primary_positive)
  literals = ids_for(meta, language, is_literal_positive)
  negatives = ids_for(meta, language, is_negative)
  lines = ['| Threshold | TP | FN | TPR | FP | FP rate | TP latency median / p90 (s) |',
           '| ---: | ---: | ---: | ---: | ---: | ---: | ---: |']

  # Only samples measured at every ladder point are counted, so the denominator
  # stays identical across rows and the FP counts are comparable.
  common = set.intersection(*[present(report, variant, language, value) for value in SWEEP])
  checked_positives = {sid for sid in positives if sid in common}
  checked_negatives = {sid for sid in negatives if sid in common}

  for threshold in SWEEP:
    hits = fired(report, variant, language, threshold)
    tp = sum(1 for sid in checked_positives if hits.get(sid))
    fp = sum(1 for sid in checked_negatives if hits.get(sid))
    latency = latencies(report, variant, language, threshold, checked_positives)
    median = quantile(latency, 0.5)
    p90 = quantile(latency, 0.9)
    latency_text = f'{median:.2f} / {p90:.2f}' if median is not None else 'n/a'
    lines.append(f'| 1e{round(math.log10(threshold))} | {tp} | {len(checked_positives) - tp} | '
                 f'{tp / max(len(checked_positives), 1):.3f} | {fp} | {fp / max(len(checked_negatives), 1):.3f} | {latency_text} |')

  hits = fired(report, variant, language, 1e-15)
  literal_hits = sum(1 for sid in literals if hits.get(sid))
  lines.append('')
  lines.append(f'literal brand spelling (not the intended pronunciation): '
               f'{literal_hits}/{len(literals)} detected at 1e-15')

  return '\n'.join(lines)


def sample_rate_table(report: dict, meta: dict[str, dict], threshold: float = 1e-15) -> str:
  """French sample-rate comparison at one threshold, plus the ladder shape."""
  lines = ['| Threshold | A TPR | B TPR | B2 TPR | A FP rate | B FP rate | B2 FP rate |',
           '| ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
  positives = ids_for(meta, 'fr', is_primary_positive)
  negatives = ids_for(meta, 'fr', is_negative)

  for value in SWEEP:
    row = [f'1e{round(math.log10(value))}']

    for variant in ('A_16k_ps16k', 'B_16k_down8k_ps8k', 'B2_16k_soxr8k_ps8k'):
      hits = fired(report, variant, 'fr', value)
      measured = present(report, variant, 'fr', value)
      checked = {sid for sid in positives if sid in measured}
      row.append(f'{sum(1 for sid in checked if hits.get(sid)) / max(len(checked), 1):.3f}')

    for variant in ('A_16k_ps16k', 'B_16k_down8k_ps8k', 'B2_16k_soxr8k_ps8k'):
      hits = fired(report, variant, 'fr', value)
      measured = present(report, variant, 'fr', value)
      checked = {sid for sid in negatives if sid in measured}
      row.append(f'{sum(1 for sid in checked if hits.get(sid)) / max(len(checked), 1):.3f}')

    lines.append('| ' + ' | '.join(row) + ' |')

  return '\n'.join(lines)


def subgroup_table(report: dict, meta: dict[str, dict], language: str, threshold: float) -> str:
  """Detection rate by label and acoustic condition at one threshold."""
  hits = fired(report, 'A_16k_ps16k', language, threshold)
  groups: dict[tuple, list[str]] = {}

  for sid, sample in meta.items():
    if sample['language'] != language:
      continue

    key = (sample['kind'], sample['label'], sample['noise'] or 'clean', sample['snr_db'])
    groups.setdefault(key, []).append(sid)

  lines = ['| Kind | Label | Noise | SNR | n | fired | rate |', '| --- | --- | --- | ---: | ---: | ---: | ---: |']

  def sort_key(item):
    key, _ = item
    return (key[0], key[1], key[2], key[3] or 0)

  for key, members in sorted(groups.items(), key=sort_key):
    count = sum(1 for sid in members if hits.get(sid))
    lines.append(f'| {key[0]} | {key[1]} | {key[2]} | {key[3] if key[3] is not None else "-"} | {len(members)} | '
                 f'{count} | {count / len(members):.2f} |')

  return '\n'.join(lines)


def false_positive_table(report: dict, meta: dict[str, dict], language: str, threshold: float) -> str:
  """Which negatives fired, grouped by label and condition."""
  hits = fired(report, 'A_16k_ps16k', language, threshold)
  rows = []

  for sid, sample in meta.items():
    if sample['language'] != language or not is_negative(sample) or not hits.get(sid):
      continue

    key = f'production-A-{language}-{threshold:g}'
    detection = next((row['detection'] for row in production_run(report, key) if row['id'] == sid), None)
    rows.append((sample['label'], sample['noise'] or 'clean', sample['snr_db'],
                 detection['hypstr'] if detection else '?', sample['text'][:44], sample['voice'] or sample['engine']))

  lines = ['| Label | Noise | SNR | hypothesis | source text | voice |', '| --- | --- | ---: | --- | --- | --- |']

  for row in sorted(rows, key=lambda r: (r[0], r[1], r[2] or 0)):
    lines.append(f'| {row[0]} | {row[1]} | {row[2] if row[2] is not None else "-"} | {row[3]!r} | {row[4]} | {row[5]} |')

  lines.append('')
  lines.append(f'{len(rows)} negatives fired at 1e{round(math.log10(threshold))}')

  return '\n'.join(lines)


def noise_table(report: dict, meta: dict[str, dict], language: str) -> str:
  """Positive detection rate by noise type and SNR at 1e-15."""
  hits = fired(report, 'A_16k_ps16k', language, 1e-15)
  buckets: dict[tuple, list[str]] = {}

  for sid, sample in meta.items():
    if sample['language'] != language or not is_primary_positive(sample) or not sample['noise']:
      continue

    buckets.setdefault((sample['noise'], sample['snr_db']), []).append(sid)

  lines = ['| Noise | SNR | n | detected | rate |', '| --- | ---: | ---: | ---: | ---: |']

  for key in sorted(buckets, key=lambda k: (k[0], k[1])):
    members = buckets[key]
    count = sum(1 for sid in members if hits.get(sid))
    lines.append(f'| {key[0]} | {key[1]} | {len(members)} | {count} | {count / len(members):.2f} |')

  return '\n'.join(lines)


def margin_summary(report: dict, meta: dict[str, dict]) -> str:
  """Reset-free margin medians per variant (all variants treated identically)."""
  lines = ['| Language | Scope | Variant | n | median prob | median log10(equiv threshold) |',
           '| --- | --- | --- | ---: | ---: | ---: |']

  for run in report['margin_runs']:
    language = run.get('language') or run['key'].split('-')[2]
    variant = run.get('variant') or run['key'].split('-')[1]

    if run.get('error'):
      lines.append(f'| {language} | {run["scope"]} | {variant} | 0 | FAILED | {run["error"][:40]} |')
      continue

    for row_language in ('fr', 'en'):
      primary = [
        row for row in run['rows']
        if row['language'] == row_language and meta[row['id']]['kind'] == 'positive'
        and meta[row['id']]['label'] == 'wakeword'
      ]

      if not primary:
        continue

      values = [row['best_prob'] for row in primary if row['best_prob'] > 0]
      logs = [math.log10(row['margin_threshold']) for row in primary if row['margin_threshold'] > 0]
      median_prob = sorted(values)[len(values) // 2] if values else 0.0
      median_log = sorted(logs)[len(logs) // 2] if logs else float('nan')
      lines.append(f'| {row_language} | {run["scope"]} | {variant} | {len(primary)} | '
                   f'{median_prob:.4f} | {median_log:.2f} |')

  return '\n'.join(lines)


def strictest_firing(report: dict, variant: str, language: str, sample_id: str) -> float | None:
  """The largest (strictest) ladder threshold at which a sample still fired."""
  short = variant.split('_')[0]
  found = None

  for run in report['production_runs']:
    parts = run['key'].split('-')

    if parts[0] != 'production' or parts[1] != short or parts[2] != language:
      continue

    threshold = float('-'.join(parts[3:]))

    for row in run['rows']:
      if row['id'] == sample_id and row['detected']:
        found = threshold if found is None else max(found, threshold)

  return found


def score_quantiles(report: dict, meta: dict[str, dict], language: str, variant: str = 'A_16k_ps16k') -> str:
  """Distribution of the strictest firing threshold per group (a reset-aware score)."""
  groups: dict[tuple, list[str]] = {}

  for sid, sample in meta.items():
    if sample['language'] != language:
      continue

    key = (sample['kind'], sample['label'], sample['noise'] or 'clean')
    groups.setdefault(key, []).append(sid)

  lines = ['| Group | n | never fired | min | p25 | median | p75 | max |',
           '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']

  for key, members in sorted(groups.items()):
    values = [strictest_firing(report, variant, language, sid) for sid in members]
    fired_values = sorted(math.log10(value) for value in values if value is not None)
    never = len(values) - len(fired_values)

    def pick(q: float) -> str:
      if not fired_values:
        return 'n/a'

      return f'{fired_values[min(len(fired_values) - 1, int(q * len(fired_values)))]:.1f}'

    lines.append(f'| {" / ".join(key)} | {len(members)} | {never} | {pick(0.0)} | {pick(0.25)} | {pick(0.5)} | '
                 f'{pick(0.75)} | {pick(1.0)} |')

  return chr(10).join(lines)


def paired_noise_table(report: dict, meta: dict[str, dict], language: str) -> str:
  """Paired clean-vs-noisy comparison on the same underlying speech."""
  hits = fired(report, 'A_16k_ps16k', language, 1e-15)
  bases: dict[str, list[dict]] = {}

  for sample in meta.values():
    if sample['language'] != language or not sample.get('base_id'):
      continue

    bases.setdefault(sample['base_id'], []).append(sample)

  lines = ['| Base | Label | clean fired | noisy fired / n | SNR 20 | SNR 10 | SNR 5 |',
           '| --- | --- | --- | ---: | ---: | ---: | ---: |']
  clean_fired_noisy_missed = 0
  clean_missed_noisy_fired = 0

  for base_id, samples in sorted(bases.items()):
    if base_id not in meta:
      continue

    base = meta[base_id]
    clean = bool(hits.get(base_id))
    noisy = [sample for sample in samples if sample['noise']]
    fired_noisy = sum(1 for sample in noisy if hits.get(sample['id']))
    per_snr = []

    for snr in (20.0, 10.0, 5.0):
      members = [sample for sample in noisy if sample['snr_db'] == snr]
      per_snr.append(str(sum(1 for sample in members if hits.get(sample['id']))) + '/' + str(len(members)))

    if clean and fired_noisy == 0:
      clean_fired_noisy_missed += 1

    if not clean and fired_noisy > 0:
      clean_missed_noisy_fired += 1

    lines.append(f'| {base_id} | {base["label"]} | {"yes" if clean else "no"} | {fired_noisy}/{len(noisy)} | '
                 + ' | '.join(per_snr) + ' |')

  lines.append('')
  lines.append(f'clean fired but every noisy variant missed: {clean_fired_noisy_missed} bases; '
               f'clean missed but some noisy variant fired: {clean_missed_noisy_fired} bases')

  return chr(10).join(lines)


def clean_breakdown(report: dict, meta: dict[str, dict], language: str) -> str:
  """Clean positives broken down by voice, speed and level."""
  hits15 = fired(report, 'A_16k_ps16k', language, 1e-15)
  hits25 = fired(report, 'A_16k_ps16k', language, 1e-25)
  buckets: dict[tuple, list[str]] = {}

  for sid, sample in meta.items():
    if sample['language'] != language or sample['kind'] != 'positive' or sample['noise']:
      continue

    if sample['label'] != 'wakeword':
      continue

    buckets.setdefault((sample['voice'], sample['speed_wpm'], sample['level']), []).append(sid)

  lines = ['| Voice | wpm | level | n | fired 1e-15 | fired 1e-25 |', '| --- | ---: | --- | ---: | ---: | ---: |']

  for key in sorted(buckets, key=lambda k: (str(k[0]), k[1] or 0, str(k[2]))):
    members = buckets[key]
    lines.append(f'| {key[0]} | {key[1]} | {key[2]} | {len(members)} | '
                 + str(sum(1 for sid in members if hits15.get(sid))) + ' | '
                 + str(sum(1 for sid in members if hits25.get(sid))) + ' |')

  return chr(10).join(lines)


def real_noise_table(report: dict, meta: dict[str, dict], language: str) -> str:
  """False-positive rate on real human speech, clean and with real noise."""
  groups: dict[str, list[dict]] = {'clean': [], 'real:fan_ac': [], 'real:keyboard_office': [],
                                   'real:street_traffic': [], 'real:babble': []}

  for sample in meta.values():
    if sample['language'] != language or sample['engine'] != 'human':
      continue

    key = 'clean' if not sample['noise'] else sample['noise']

    if key in groups:
      groups[key].append(sample)

  lines = ['| Real human negatives | n | fired 1e-10 | fired 1e-15 | fired 1e-20 |',
           '| --- | ---: | ---: | ---: | ---: |']

  for key, members in groups.items():
    if not members:
      continue

    counts = []

    for threshold in (1e-10, 1e-15, 1e-20):
      hits = fired(report, 'A_16k_ps16k', language, threshold)
      measured = present(report, 'A_16k_ps16k', language, threshold)
      checked = [sample for sample in members if sample['id'] in measured]
      count = sum(1 for sample in checked if hits.get(sample['id']))
      counts.append(f'{count}/{len(checked)}')

    lines.append(f'| {key} | {len(members)} | ' + ' | '.join(counts) + ' |')

  return chr(10).join(lines)


def main() -> None:
  parser = argparse.ArgumentParser(description='Analyse the wake-word study results.')
  parser.add_argument('--results', default=str(corpus.STUDY_DIR / 'results.json'))
  parser.add_argument('--section', default='all',
                      choices=['all', 'sweep', 'sample_rate', 'subgroups', 'fp', 'noise', 'margins',
                               'errors', 'scores', 'paired', 'breakdown', 'realnoise'])
  args = parser.parse_args()

  report = load(Path(args.results))
  meta = metadata()
  output: list[str] = []
  output.append(f"manifest counts: {report['manifest_counts']}")
  output.append(f"runs: {len(report['margin_runs'])} margin / {len(report['production_runs'])} production, "
                f"elapsed {report['elapsed_s']}s, pocketsphinx {report['environment'].get('pocketsphinx_version')}")

  if args.section in ('all', 'errors'):
    found = errors(report)

    for key, message in sorted(found.items()):
      output.append(f'ERROR {key}: {message}')

  if args.section in ('all', 'sweep'):
    for language in ('fr', 'en'):
      output.append(f'\n## Threshold sweep — {language} (production semantics, all {report["manifest_counts"]} samples)')
      output.append(sweep_table(report, meta, language))

  if args.section in ('all', 'sample_rate'):
    output.append('\n## French sample-rate comparison (production semantics)')
    output.append(sample_rate_table(report, meta))
    output.append('\n## Reset-free margin pass (variant side-by-side)')
    output.append(margin_summary(report, meta))

  if args.section in ('all', 'noise'):
    for language in ('fr', 'en'):
      output.append(f'\n## Positives by noise condition at 1e-15 — {language}')
      output.append(noise_table(report, meta, language))

  if args.section in ('all', 'subgroups'):
    for language in ('fr', 'en'):
      output.append(f'\n## Subgroups at 1e-15 — {language}')
      output.append(subgroup_table(report, meta, language, 1e-15))

  if args.section in ('all', 'fp'):
    for language in ('fr', 'en'):
      output.append(f'\n## False positives at 1e-15 — {language}')
      output.append(false_positive_table(report, meta, language, 1e-15))
      output.append(f'\n## False positives at 1e-10 — {language}')
      output.append(false_positive_table(report, meta, language, 1e-10))

  if args.section in ('all', 'scores'):
    for language in ('fr', 'en'):
      output.append('## Score distribution (strictest firing threshold) - ' + language)
      output.append(score_quantiles(report, meta, language))

  if args.section in ('all', 'paired'):
    for language in ('fr', 'en'):
      output.append('## Paired clean vs noisy (same speech) at 1e-15 - ' + language)
      output.append(paired_noise_table(report, meta, language))

  if args.section in ('all', 'breakdown'):
    for language in ('fr', 'en'):
      output.append('## Clean positives by voice/speed/level - ' + language)
      output.append(clean_breakdown(report, meta, language))

  if args.section in ('all', 'realnoise'):
    for language in ('fr', 'en'):
      output.append('## Real human speech + real noise (false positives) - ' + language)
      output.append(real_noise_table(report, meta, language))

  text = '\n'.join(output)
  (corpus.STUDY_DIR / 'analysis.md').write_text(text, encoding='utf-8')
  print(text)


if __name__ == '__main__':
  main()
