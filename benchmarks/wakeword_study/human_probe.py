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
"""Can the French model spot known French words in real human speech?

The wake-word corpus has no human recordings, so every positive number in the study
is a TTS number. This probe sidesteps that: it takes real human French recordings
(African Accented French, 16 kHz) whose transcript contains a word that is already in
the model dictionary, makes that word the KWS keyphrase, and measures whether the
decoder fires on the human utterance that contains it versus human utterances that
do not.

If the model cannot fire on in-vocabulary words in real human speech at 1e-15, then no
wake-word transcription can rescue French recall at that threshold.
"""
import argparse
import json
import math
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wakeword_study import corpus as corpus
from wakeword_study import psprobe

from ohunerin.core.package import APP_NAME
from pocketsphinx import Config  # type: ignore[import-untyped]
from pocketsphinx import Decoder

MODEL = corpus.BASE_DIR / 'models/wakeword-fr/cmusphinx-fr-ptm-8khz-5.2'
DICTIONARY = corpus.BASE_DIR / 'models/wakeword-fr/pronounciation-dictionary.dict'

#: Words in both the model dictionary and the AFF vocabulary. The ones also present in
#: model_probe.WORDS allow a direct TTS-vs-human comparison of the same word.
TARGET_WORDS = ['premier', 'femme', 'maison', 'bonjour', 'famille', 'soleil', 'mardi',
                'enfant', 'travail', 'temps', 'monsieur', 'chose', 'jour', 'monde',
                'homme', 'vie', 'main', 'école', 'argent', 'matin', 'soir', 'année',
                'pays', 'gens', 'moment', 'place', 'état', 'père', 'mère', 'frère',
                'affaire', 'problème', 'idée', 'pomme', 'mot', 'or', 'mort', 'note',
                'opéra', 'oreille', 'marché', 'été']
MAX_POSITIVES = 12
MAX_NEGATIVES = 40
MIN_SECONDS = 1.0
MAX_SECONDS = 6.0
CHUNK_SECONDS = 0.05
PAD_SECONDS = 0.5
PROBE_MANIFEST = corpus.STUDY_DIR / 'human_probe_manifest.json'


def dictionary_phones(word: str) -> str | None:
  """Phone sequence the model dictionary gives a word."""
  for line in DICTIONARY.read_text(encoding='utf-8', errors='replace').splitlines():
    key, _, phones = line.partition(' ')

    if key == word:
      return phones.strip()

  return None


def build_manifest() -> dict:
  """Select AFF utterances that contain each target word, plus shared negatives."""
  entries = corpus.aff_index()
  words: dict[str, dict] = {}
  used: set[str] = set()

  for word in TARGET_WORDS:
    phones = dictionary_phones(word)

    if phones is None:
      continue

    pattern = re.compile(rf'\b{word}s?\b', re.IGNORECASE)
    picks = []

    for utterance, text, path in entries:
      if utterance in used or not pattern.search(text):
        continue

      seconds = path.stat().st_size / 2 / 16000

      if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        continue

      picks.append({'id': f'human-{word}-{utterance}', 'path': str(path), 'text': text})
      used.add(utterance)

      if len(picks) >= MAX_POSITIVES:
        break

    if picks:
      words[word] = {'phones': phones, 'utterances': picks}

  negatives = []

  for utterance, text, path in entries:
    if utterance in used:
      continue

    if any(re.search(rf'\b{word}s?\b', text, re.IGNORECASE) for word in words):
      continue

    seconds = path.stat().st_size / 2 / 16000

    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
      continue

    negatives.append({'id': f'human-neg-{utterance}', 'path': str(path), 'text': text})
    used.add(utterance)

    if len(negatives) >= MAX_NEGATIVES:
      break

  manifest = {'words': words, 'negatives': negatives,
              'provenance': 'African Accented French, OpenSLR SLR57 (CC BY-SA 4.0), real human speakers'}
  PROBE_MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
  print(f'selected {len(words)} words, {sum(len(v["utterances"]) for v in words.values())} positives, '
        f'{len(negatives)} negatives')

  return manifest


def probe_word(payload: dict) -> dict:
  """Worker: margin pass for one keyphrase over human positives and shared negatives."""
  started = time.perf_counter()
  word = payload['word']
  directory = tempfile.mkdtemp(prefix='ohunerin-human-')
  keyfile = os.path.join(directory, 'keyphrases.list')
  Path(keyfile).write_text(f'{word}\n', encoding='utf-8')
  config = Config(lm=None, hmm=str(MODEL), dict=str(DICTIONARY),
                  kws_threshold=psprobe.MARGIN_THRESHOLD)
  decoder = Decoder(config)
  decoder.add_kws(APP_NAME, keyfile)
  decoder.activate_search(APP_NAME)
  step = int(16000 * CHUNK_SECONDS) * 2
  rows = []

  for role, sample in (('positive', s) for s in payload['positives']):
    rows.append(run_one(decoder, word, role, sample, step))

  for sample in payload['negatives']:
    rows.append(run_one(decoder, word, 'negative', sample, step))

  return {'key': word, 'word': word, 'phones': payload['phones'], 'rows': rows,
          'elapsed_s': round(time.perf_counter() - started, 3)}


def run_one(decoder: Decoder, word: str, role: str, sample: dict, step: int) -> dict:
  """One permissive no-reset margin pass over a single recording."""
  audio = corpus.decode_raw(Path(sample['path']).read_bytes())
  pad = np.zeros(int(PAD_SECONDS * 16000))
  stream = corpus.encode_raw(np.concatenate([pad, audio, pad]))
  decoder.reinit_feat()
  decoder.start_utt()
  best = 0.0

  for position in range(0, len(stream), step):
    decoder.process_raw(stream[position:position + step], False, False)
    segments = decoder.seg()
    segments = list(segments) if segments is not None else []

    for segment in segments:
      if segment.word == word:
        best = max(best, float(segment.prob))

  decoder.end_utt()

  return {'id': sample['id'], 'role': role, 'text': sample['text'],
          'word': word, 'best_prob': best,
          'margin_threshold': psprobe.prob_to_threshold(best)}


def main() -> None:
  parser = argparse.ArgumentParser(description='French model probe on real human speech.')
  parser.add_argument('--stage', choices=['build', 'run'], default='run')
  parser.add_argument('--workers', type=int, default=min(10, os.cpu_count() or 4))
  args = parser.parse_args()

  if args.stage == 'build' or not PROBE_MANIFEST.exists():
    manifest = build_manifest()
  else:
    manifest = json.loads(PROBE_MANIFEST.read_text(encoding='utf-8'))

  if args.stage == 'build':
    return

  negatives = manifest['negatives']
  jobs = [{'word': word, 'phones': value['phones'], 'positives': value['utterances'],
           'negatives': negatives} for word, value in manifest['words'].items()]
  print(f'running {len(jobs)} human word probes', flush=True)
  started = time.perf_counter()
  results = []

  with ProcessPoolExecutor(max_workers=args.workers) as pool:
    for result in pool.map(probe_word, jobs):
      print(f"  {result['key']}: {len(result['rows'])} rows in {result['elapsed_s']}s", flush=True)
      results.append(result)

  out = corpus.STUDY_DIR / 'human_probe_results.json'
  out.write_text(json.dumps({'jobs': results}), encoding='utf-8')
  print(f'wrote {out} in {time.perf_counter() - started:.0f}s')
  print('| Word | dictionary phones | human positives >= 1e-15 | median log10 margin | negatives >= 1e-15 |')
  print('| --- | --- | ---: | ---: | ---: |')

  for result in results:
    pos = [row for row in result['rows'] if row['role'] == 'positive']
    neg = [row for row in result['rows'] if row['role'] == 'negative']
    hits = sum(1 for row in pos if row['margin_threshold'] >= 1e-15)
    neg_hits = sum(1 for row in neg if row['margin_threshold'] >= 1e-15)
    logs = sorted(math.log10(row['margin_threshold']) for row in pos if row['margin_threshold'] > 0)
    median = f'{logs[len(logs) // 2]:.1f}' if logs else 'never'
    print(f"| {result['word']} | {result['phones']} | {hits}/{len(pos)} | {median} | {neg_hits}/{len(neg)} |")


if __name__ == '__main__':
  main()
