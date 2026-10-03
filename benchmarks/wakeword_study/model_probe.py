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
"""Acoustic-model sanity probe on the model own vocabulary.

Before blaming the wake-word transcription, check whether the French acoustic model
recognises plain French words that are already in its dictionary, with the exact
pronunciation the dictionary gives them. Each word becomes its own one-word KWS
keyphrase and is synthesized by espeak-ng spelling TTS across eight voices.

If the model cannot fire on mot (mm au, /o/), pomme (pp oo mm, /ɔ/) or rémi
(rr ei mm ii, /e/) at 1e-15, then the wake-word recall ceiling is a property of the
model and the threshold, not of the wake-word transcription.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wakeword_study import corpus as corpus
from wakeword_study import psprobe

from ohunerin.core.package import APP_NAME
from pocketsphinx import Config  # type: ignore[import-untyped]
from pocketsphinx import Decoder

MODEL = corpus.BASE_DIR / 'models/wakeword-fr/cmusphinx-fr-ptm-8khz-5.2'
DICTIONARY = corpus.BASE_DIR / 'models/wakeword-fr/pronounciation-dictionary.dict'

#: Words chosen to cover the phone contrasts that matter for the wake word. All of
#: them are present in the model own dictionary, so no transcription is invented.
WORDS = ['pomme', 'mot', 'beau', 'chose', 'rose', 'or', 'mort', 'note', 'vélo', 'moto',
         'rémi', 'très', 'omelette', 'opéra', 'menu', 'oreille', 'orage', 'orange', 'auréole',
         'café', 'bébé', 'marché', 'été', 'année', 'idée', 'musée', 'préféré', 'premier',
         'chevalier', 'aimer', 'soleil', 'pareil', 'réveil', 'problème', 'système', 'même',
         'frère', 'mère', 'père', 'affaire']
VOICES = ['fr', 'fr+f1', 'fr+f2', 'fr+f3', 'fr+m1', 'fr+m2', 'fr-be', 'fr-ch']
WPM = 135
PROBE_DIR = corpus.STUDY_DIR / 'modelprobe'
PROBE_MANIFEST = corpus.STUDY_DIR / 'model_probe_manifest.json'
CHUNK_SECONDS = 0.05
PAD_SECONDS = 0.5


def dictionary_phones(word: str) -> str | None:
  """Phone sequence the model dictionary gives a word."""
  for line in DICTIONARY.read_text(encoding='utf-8', errors='replace').splitlines():
    key, _, phones = line.partition(' ')
    key = key.replace('é', 'e')

    if key == word.replace('é', 'e'):
      return phones.strip()

  return None


def espeak_ipa(text: str, voice: str = 'fr') -> str:
  """IPA espeak-ng renders for a spelling."""
  result = subprocess.run(['espeak-ng', '-q', '--ipa', '-v', voice, text], capture_output=True, text=True)

  return result.stdout.strip()


def build_corpus() -> dict:
  """Synthesize one clip per (word, voice) and write the manifest."""
  PROBE_DIR.mkdir(parents=True, exist_ok=True)
  tmp = corpus.STUDY_DIR / 'modelprobe_tmp'
  tmp.mkdir(parents=True, exist_ok=True)
  samples = []
  words = {}

  for word in WORDS:
    phones = dictionary_phones(word)

    if phones is None:
      print(f'  skip {word}: not in dictionary', flush=True)
      continue

    words[word] = {'phones': phones, 'ipa': espeak_ipa(word)}

    for voice in VOICES:
      wav = tmp / 'w.wav'
      result = subprocess.run(
        ['espeak-ng', '-v', voice, '-s', str(WPM), '-p', '50', '-a', '150', '-w', str(wav), word],
        capture_output=True,
      )

      if result.returncode != 0 or not wav.exists():
        continue

      sample_id = f'model-{word}-{voice.replace("+", "_")}'
      meta = corpus.write_raw(f'modelprobe/{sample_id}.raw', corpus.decode_to_float(wav))
      samples.append({
        'id': sample_id, 'language': 'fr', 'kind': 'positive', 'label': 'wakeword',
        'word': word, 'dictionary_phones': phones, 'espeak_ipa': words[word]['ipa'],
        'text': word, 'engine': 'espeak-ng', 'voice': voice, 'noise': None, 'snr_db': None,
        'provenance': f'espeak-ng spelling TTS of {word!r} (IPA {words[word]["ipa"]}), dictionary {phones}',
        **meta,
      })

  manifest = {'words': words, 'voices': VOICES, 'wpm': WPM, 'samples': samples}
  PROBE_MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
  print(f'wrote {len(samples)} clips for {len(words)} words')

  return manifest


def probe_word(payload: dict) -> dict:
  """Worker: margin + production verdict for one keyphrase word."""
  started = time.perf_counter()
  word = payload['word']
  directory = tempfile.mkdtemp(prefix='ohunerin-model-')
  keyfile = os.path.join(directory, 'keyphrases.list')
  Path(keyfile).write_text(f'{word}\n', encoding='utf-8')
  config = Config(lm=None, hmm=str(MODEL), dict=str(DICTIONARY),
                  kws_threshold=psprobe.MARGIN_THRESHOLD)
  decoder = Decoder(config)
  decoder.add_kws(APP_NAME, keyfile)
  decoder.activate_search(APP_NAME)
  step = int(16000 * CHUNK_SECONDS) * 2
  rows = []

  for sample in payload['samples']:
    import numpy as np

    audio = corpus.decode_raw((corpus.STUDY_DIR / sample['path']).read_bytes())
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
    rows.append({
      'id': sample['id'], 'word': word, 'voice': sample['voice'],
      'dictionary_phones': sample['dictionary_phones'], 'espeak_ipa': sample['espeak_ipa'],
      'best_prob': best, 'margin_threshold': psprobe.prob_to_threshold(best),
    })

  return {'key': word, 'word': word, 'rows': rows, 'elapsed_s': round(time.perf_counter() - started, 3)}


def main() -> None:
  parser = argparse.ArgumentParser(description='French acoustic-model vocabulary probe.')
  parser.add_argument('--stage', choices=['build', 'run'], default='run')
  parser.add_argument('--workers', type=int, default=min(10, os.cpu_count() or 4))
  args = parser.parse_args()

  if args.stage == 'build' or not PROBE_MANIFEST.exists():
    manifest = build_corpus()
  else:
    manifest = json.loads(PROBE_MANIFEST.read_text(encoding='utf-8'))

  if args.stage == 'build':
    return

  words = manifest['words']
  jobs = [{'word': word, 'samples': [s for s in manifest['samples'] if s['word'] == word]} for word in words]
  print(f'running {len(jobs)} word probes', flush=True)
  started = time.perf_counter()
  results = []

  with ProcessPoolExecutor(max_workers=args.workers) as pool:
    for result in pool.map(probe_word, jobs):
      print(f"  {result['key']}: {len(result['rows'])} rows in {result['elapsed_s']}s", flush=True)
      results.append(result)

  out = corpus.STUDY_DIR / 'model_probe_results.json'
  out.write_text(json.dumps({'jobs': results}), encoding='utf-8')
  print(f'wrote {out} in {time.perf_counter() - started:.0f}s')

  print('| Word | dictionary phones | espeak IPA | clips | median log10(equiv thr) | above 1e-15 |')
  print('| --- | --- | --- | ---: | ---: | ---: |')

  for result in results:
    rows = result['rows']
    logs = sorted(math.log10(row['margin_threshold']) for row in rows if row['margin_threshold'] > 0)
    median = f'{logs[len(logs) // 2]:.1f}' if logs else 'never'
    above = sum(1 for value in logs if value >= -15)
    print(f"| {result['word']} | {rows[0]['dictionary_phones']} | {rows[0]['espeak_ipa']} | {len(rows)} | "
          f'{median} | {above}/{len(rows)} |')


if __name__ == '__main__':
  main()
