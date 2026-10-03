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
"""Controlled pronunciation benchmark for the French wake word.

Context established before this module was written:

* the French dictionary maps the phone token oo to /ɔ/ (pomme pp oo mm, or oo rr,
  omelette oo mm ee ll ai tt), au to /o/ (mot mm au, beau bb au), ou to /u/,
  ei to /e/ (rémi rr ei mm ii), ai to /ɛ/ and ee to /ə/ (petit pp ee tt ii);
* configuration asks for three pronunciations of oremi
  (oo rr ei mm ii = /ɔʁemi/, oo rr ai mm ii = /ɔʁɛmi/, au rr ei mm ii = /oʁemi/)
  but WakewordEngine only writes entry.word into the keyphrase file, and
  kws_search_reinit() resolves a keyphrase with dict_wordid() + dict_pron(),
  which never expands the oremi(2) / oremi(3) alternates.

So the search only ever sees /ɔʁemi/. This module tests that claim and measures
the alternatives on identical audio.

Clips are synthesized with espeak-ng phoneme input ([[...]]), not spelling, so the
pronunciation under test is exact and independently verifiable with espeak-ng --ipa.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wakeword_study import corpus as corpus

from ohunerin.core.package import APP_NAME
from ohunerin.engines.wakeword import is_discriminant_word
from ohunerin.models.wakeword import DictionaryEntry
from pocketsphinx import Config  # type: ignore[import-untyped]
from pocketsphinx import Decoder

PRON_DIR = corpus.STUDY_DIR / 'pron'
PRON_MANIFEST = corpus.STUDY_DIR / 'pronunciation_manifest.json'
CHUNK_SECONDS = 0.05
PAD_SECONDS = 0.5

#: espeak-ng phoneme input (mnemonics from espeak-ng -q -x) and the IPA it renders.
#: The IPA string is what espeak-ng --ipa reports for the same input, verified at
#: build time and stored in the manifest.
PRONUNCIATIONS: dict[str, tuple[str, str]] = {
  'o_re': ("[[o rem'i]]", 'o ʁe mi'),          # au rémi / ô rémi
  'openo_re': ("[[O rem'i]]", 'ɔ ʁe mi'),      # orémi (open o)
  'o_openE': ("[[o rE m'i]]", 'o ʁɛ mi'),      # orèmi
  'openo_openE': ("[[O rE m'i]]", 'ɔ ʁɛ mi'),
  'o_schwa': ("[[o r@ m'i]]", 'o ʁə mi'),      # o-re-mi, schwa
  'openo_schwa': ("[[O r@ m'i]]", 'ɔ ʁə mi'),
  'o_elide': ("[[o rm'i]]", 'o ʁmi'),          # or'mi, elided vowel
  'openo_elide': ("[[O rm'i]]", 'ɔ ʁmi'),
}

VOICES = ['fr', 'fr+f1', 'fr+f2', 'fr+f3', 'fr+m1', 'fr+m2', 'fr+m3', 'fr-be', 'fr-ch']
SPEEDS = [110, 150]

#: Keyphrase/dictionary configurations. 'phones' is the pronunciation given to the
#: base dictionary word oremi; 'keys' is the exact keyphrase file content.
KWS_VARIANTS: dict[str, dict] = {
  'current': {
    'phones': ['oo rr ei mm ii', 'oo rr ai mm ii', 'au rr ei mm ii'],
    'keys': ['oremi'], 'note': 'production: base word only, KWS sees /ɔʁemi/',
  },
  'primary_o': {
    'phones': ['au rr ei mm ii'], 'keys': ['oremi'],
    'note': 'base pronunciation moved to /oʁemi/',
  },
  'primary_openE': {
    'phones': ['oo rr ai mm ii'], 'keys': ['oremi'],
    'note': 'base pronunciation /ɔʁɛmi/',
  },
  'primary_o_schwa': {
    'phones': ['au rr ee mm ii'], 'keys': ['oremi'],
    'note': 'base pronunciation /oʁəmi/ (schwa = ee)',
  },
  'primary_o_elide': {
    'phones': ['au rr mm ii'], 'keys': ['oremi'],
    'note': 'base pronunciation /oʁmi/',
  },
  'multi_keys': {
    'phones': ['oo rr ei mm ii', 'oo rr ai mm ii', 'au rr ei mm ii'],
    'keys': ['oremi', 'oremi(2)', 'oremi(3)'],
    'note': 'all three configured pronunciations as separate keyphrases',
  },
  'multi_keys2': {
    'phones': ['oo rr ei mm ii', 'au rr ei mm ii'],
    'keys': ['oremi', 'oremi(2)'],
    'note': 'open-o and closed-o variants both searched',
  },
  'primary_o_no_discriminant': {
    'phones': ['au rr ei mm ii'], 'keys': ['oremi', 'dikomlam'],
    'note': 'control: no remi keyphrase at all',
  },
  'current_no_discriminant': {
    'phones': ['oo rr ei mm ii', 'oo rr ai mm ii', 'au rr ei mm ii'],
    'keys': ['oremi'], 'note': 'control: current phones, no remi keyphrase',
  },
  'en_current': {
    'language': 'en',
    'phones': ['OW R EH M IY', 'OW R EY M IY', 'AO R EH M IY', 'AO R EY M IY'],
    'discriminant_phones': ['R EH M IY', 'R EY M IY'],
    'keys': ['oremi'], 'note': 'production English: base word only',
  },
  'en_multi': {
    'language': 'en',
    'phones': ['OW R EH M IY', 'OW R EY M IY', 'AO R EH M IY', 'AO R EY M IY'],
    'discriminant_phones': ['R EH M IY', 'R EY M IY'],
    'keys': ['oremi', 'oremi(2)', 'oremi(3)', 'oremi(4)'],
    'note': 'all four configured English pronunciations as keyphrases',
  },
  'en_multi2': {
    'language': 'en',
    'phones': ['OW R EH M IY', 'OW R EY M IY'],
    'discriminant_phones': ['R EH M IY', 'R EY M IY'],
    'keys': ['oremi', 'oremi(2)'],
    'note': 'the two OW->EH/EY English variants',
  },
}

#: Model and dictionary per language, mirroring server/http.py LANGUAGE_MODEL_PATHS.
LANGS = {
  'fr': (corpus.BASE_DIR / 'models/wakeword-fr/cmusphinx-fr-ptm-8khz-5.2',
         corpus.BASE_DIR / 'models/wakeword-fr/pronounciation-dictionary.dict'),
  'en': (corpus.BASE_DIR / 'models/wakeword-en/acoustic-model',
         corpus.BASE_DIR / 'models/wakeword-en/pronounciation-dictionary.dict'),
}

#: Wake words and discriminants carried over from config.json.
DISCRIMINANTS = ['remi']
DISCRIMINANTS_EN = ['remi']
OTHER_WAKEWORDS = ['dikomlam']


def espeak_ipa(phonemes: str) -> str:
  """Return the IPA espeak-ng renders for a phoneme input string."""
  result = subprocess.run(['espeak-ng', '-q', '--ipa', '-v', 'fr', phonemes], capture_output=True, text=True)

  return result.stdout.strip()


def synth_phonemes(phonemes: str, voice: str, wpm: int, out: Path) -> bool:
  """Synthesize a phoneme string with espeak-ng at a given voice and speed."""
  result = subprocess.run(
    ['espeak-ng', '-v', voice, '-s', str(wpm), '-p', '50', '-a', '150', '-w', str(out), phonemes],
    capture_output=True,
  )

  return result.returncode == 0 and out.exists() and out.stat().st_size > 0


def build_corpus() -> dict:
  """Synthesize the controlled pronunciation corpus and write its manifest."""
  PRON_DIR.mkdir(parents=True, exist_ok=True)
  tmp = corpus.STUDY_DIR / 'pron_tmp'
  tmp.mkdir(parents=True, exist_ok=True)
  samples: list[dict] = []

  for name, (phonemes, expected_ipa) in PRONUNCIATIONS.items():
    actual_ipa = espeak_ipa(phonemes)

    for voice in VOICES:
      for wpm in SPEEDS:
        wav = tmp / 'p.wav'

        if not synth_phonemes(phonemes, voice, wpm, wav):
          print(f'  skip {name} {voice} {wpm}', flush=True)
          continue

        audio = corpus.decode_to_float(wav)
        sample_id = f'pron-{name}-{voice.replace("+", "_")}-{wpm}'
        meta = corpus.write_raw(f'pron/{sample_id}.raw', audio)
        samples.append({
          'id': sample_id, 'language': 'fr', 'kind': 'positive', 'label': 'wakeword',
          'text': phonemes, 'engine': 'espeak-ng-phonemes', 'voice': f'{voice}@{wpm}',
          'speaker': None, 'pronunciation': name, 'expected_ipa': expected_ipa,
          'actual_ipa': actual_ipa, 'noise': None, 'snr_db': None,
          'provenance': f'espeak-ng 1.52 phoneme input {phonemes} (IPA {actual_ipa}), voice {voice}, {wpm} wpm',
          **meta,
        })

  manifest = {
    'pronunciations': {name: {'espeak': value[0], 'ipa': value[1]} for name, value in PRONUNCIATIONS.items()},
    'voices': VOICES, 'speeds': SPEEDS,
    'counts': {'total': len(samples)},
    'samples': samples,
  }
  PRON_MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
  print(f'wrote {len(samples)} controlled pronunciation clips')

  return manifest


class VariantDecoder:
  """A PocketSphinx KWS decoder with an explicit keyphrase/dictionary layout."""

  def __init__(self, spec: dict, threshold: float) -> None:
    self.spec = spec
    self.threshold = threshold
    config_spec = spec
    directory = tempfile.mkdtemp(prefix='ohunerin-pron-')
    self.keyfile = os.path.join(directory, 'keyphrases.list')
    keys = list(config_spec['keys'])

    with open(self.keyfile, 'w', encoding='utf-8') as file:
      for key in keys:
        file.write(f'{key}\n')

    language = config_spec.get('language', 'fr')
    self.language = language
    model, dictionary = LANGS[language]
    config = Config(lm=None, hmm=str(model), dict=str(dictionary), kws_threshold=threshold)
    self.decoder = Decoder(config)
    base = config_spec.get('base', 'oremi')

    for index, phone in enumerate(config_spec['phones']):
      word = base if index == 0 else f'{base}({index + 1})'

      try:
        self.decoder.add_word(word, phone)
      except RuntimeError:
        pass

    for index, phone in enumerate(config_spec.get('discriminant_phones', ['rr ei mm ii', 'rr ai mm ii'])):
      word = 'remi' if index == 0 else f'remi({index + 1})'

      try:
        self.decoder.add_word(word, phone)
      except RuntimeError:
        pass

    self.decoder.add_kws(APP_NAME, self.keyfile)
    self.decoder.activate_search(APP_NAME)
    self.setting = _setting_for_keys(keys)

  def reset(self) -> None:
    """Reinitialize the feature extractor and open a fresh utterance."""
    self.decoder.reinit_feat()
    self.decoder.start_utt()

  def close(self) -> None:
    """End the utterance (best effort)."""
    try:
      self.decoder.end_utt()
    except RuntimeError:
      pass


def _setting_for_keys(keys: list[str]):
  """Build a WakewordSetting-like object whose discriminants match the key list."""
  from ohunerin.models.wakeword import WakewordSetting

  return WakewordSetting(
    model='', dictionary='',
    wakewords=[DictionaryEntry(word=key, phones=['x']) for key in keys if key not in DISCRIMINANTS],
    discriminants=[DictionaryEntry(word=word, phones=['x']) for word in DISCRIMINANTS],
  )


def hit_words(spec: dict) -> set[str]:
  """Keyphrases that count as wake-word hits for a variant spec."""
  discriminants = DISCRIMINANTS_EN if spec.get('language') == 'en' else DISCRIMINANTS

  return {key for key in spec['keys'] if key.split('(')[0] not in discriminants}


def margin_variant(payload: dict) -> dict:
  """Worker: permissive no-reset margin pass for one variant over a sample list.

  The margin trajectory does not depend on the threshold, so one pass yields a
  continuous score per sample that can be compared across variants in a paired
  way, which is far more sensitive than a single binary threshold.
  """
  from wakeword_study import psprobe

  started = time.perf_counter()
  spec = payload['spec']
  decoder = VariantDecoder(spec, psprobe.MARGIN_THRESHOLD)
  step = int(16000 * CHUNK_SECONDS) * 2
  wanted = hit_words(spec)
  rows = []

  for sample in payload['samples']:
    audio = corpus.decode_raw((corpus.STUDY_DIR / sample['path']).read_bytes())
    stream = padded_stream(audio)
    decoder.reset()
    best = 0.0
    best_frame = None

    for position in range(0, len(stream), step):
      decoder.decoder.process_raw(stream[position:position + step], False, False)
      segments = decoder.decoder.seg()
      segments = list(segments) if segments is not None else []

      for segment in segments:
        if segment.word in wanted:
          probability = float(segment.prob)

          if probability > best:
            best = probability
            best_frame = int(segment.end_frame)

    decoder.close()
    rows.append({
      'id': sample['id'], 'kind': sample['kind'], 'label': sample['label'],
      'pronunciation': sample.get('pronunciation'), 'voice': sample.get('voice'),
      'best_prob': best,
      'margin_threshold': psprobe.prob_to_threshold(best),
      'best_frame': best_frame,
    })

  return {'key': payload['key'], 'variant': payload['key'], 'spec': spec,
          'rows': rows, 'elapsed_s': round(time.perf_counter() - started, 3)}


def padded_stream(audio, rate: int = 16000) -> bytes:
  """Silence + audio + silence as s16le PCM."""
  import numpy as np

  pad = np.zeros(int(PAD_SECONDS * rate))

  return corpus.encode_raw(np.concatenate([pad, audio, pad]))


def run_variant(payload: dict) -> dict:
  """Worker: run one variant at one threshold over a sample list."""
  started = time.perf_counter()
  decoder = VariantDecoder(KWS_VARIANTS[payload['variant']], payload['threshold'])
  step = int(16000 * CHUNK_SECONDS) * 2
  rows = []

  for sample in payload['samples']:
    audio = corpus.decode_raw((corpus.STUDY_DIR / sample['path']).read_bytes())
    stream = padded_stream(audio)
    decoder.reset()
    detection = None
    consumed = 0

    while consumed < len(stream):
      part = stream[consumed:consumed + step]
      consumed += len(part)
      decoder.decoder.process_raw(part, False, False)
      hypothesis = decoder.decoder.hyp()

      if hypothesis:
        is_discriminant = is_discriminant_word(decoder.setting, hypothesis.hypstr)

        if not is_discriminant and detection is None:
          segments = decoder.decoder.seg()
          segments = list(segments) if segments is not None else []
          end_frame = max((int(segment.end_frame) for segment in segments), default=None)
          detection = {
            'hypstr': hypothesis.hypstr,
            'end_frame': end_frame,
            'latency_s': round(end_frame * 0.01 - PAD_SECONDS, 3) if end_frame is not None else None,
          }

        decoder.decoder.end_utt()
        decoder.reset()

    decoder.close()
    rows.append({
      'id': sample['id'], 'kind': sample['kind'], 'label': sample['label'],
      'pronunciation': sample.get('pronunciation'), 'voice': sample.get('voice'),
      'variant': payload['variant'], 'threshold': payload['threshold'],
      'detected': detection is not None, 'detection': detection,
      'latency_s': detection['latency_s'] if detection else None,
    })

  return {'key': payload['key'], 'variant': payload['variant'], 'threshold': payload['threshold'],
          'rows': rows, 'elapsed_s': round(time.perf_counter() - started, 3)}


def run_jobs(jobs: list[dict], workers: int) -> list[dict]:
  """Execute variant jobs in a process pool."""
  results = []

  with ProcessPoolExecutor(max_workers=workers) as pool:
    for result in pool.map(run_variant, jobs):
      print(f"  {result['key']}: {len(result['rows'])} rows in {result['elapsed_s']}s", flush=True)
      results.append(result)

  return results


def main() -> None:
  parser = argparse.ArgumentParser(description='Controlled pronunciation benchmark.')
  parser.add_argument('--stage', choices=['build', 'screen', 'full', 'margins'], default='screen')
  parser.add_argument('--workers', type=int, default=min(12, os.cpu_count() or 4))
  parser.add_argument('--thresholds', default='1e-15')
  parser.add_argument('--variants', default=','.join(KWS_VARIANTS))
  parser.add_argument('--out', default=str(corpus.STUDY_DIR / 'pronunciation_results.json'))
  args = parser.parse_args()

  if args.stage == 'build':
    build_corpus()
    return

  if not PRON_MANIFEST.exists():
    build_corpus()

  pronunciation = json.loads(PRON_MANIFEST.read_text(encoding='utf-8'))['samples']
  study = json.loads(corpus.MANIFEST.read_text(encoding='utf-8'))['samples']

  if args.stage == 'screen':
    existing = [s for s in study if s['language'] == 'fr' and (
      (s['kind'] == 'positive' and not s['noise']) or s['kind'] == 'negative')]
    samples = pronunciation + existing
  else:
    samples = pronunciation + study

  thresholds = [float(value) for value in args.thresholds.split(',')]
  variants = args.variants.split(',')
  jobs = []

  if args.stage == 'margins':
    margin_jobs = [{'key': variant, 'spec': KWS_VARIANTS[variant], 'samples': samples} for variant in variants]
    print(f'running {len(margin_jobs)} margin jobs over {len(samples)} samples', flush=True)
    margin_started = time.perf_counter()
    margin_results = []

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
      for result in pool.map(margin_variant, margin_jobs):
        print(f"  {result['key']}: {len(result['rows'])} rows in {result['elapsed_s']}s", flush=True)
        margin_results.append(result)

    margin_out = Path(args.out)
    margin_out.write_text(json.dumps({'jobs': margin_results, 'sample_count': len(samples)}), encoding='utf-8')
    print(f'wrote {margin_out} in {time.perf_counter() - margin_started:.0f}s')
    return

  for variant in variants:
    for threshold in thresholds:
      jobs.append({
        'key': f'{variant}-{threshold:g}', 'variant': variant, 'threshold': threshold,
        'samples': samples,
      })

  print(f'running {len(jobs)} jobs over {len(samples)} samples', flush=True)
  started = time.perf_counter()
  results = run_jobs(jobs, args.workers)
  Path(args.out).write_text(json.dumps({'jobs': results, 'sample_count': len(samples)}), encoding='utf-8')
  print(f'wrote {args.out} in {time.perf_counter() - started:.0f}s')


if __name__ == '__main__':
  main()
