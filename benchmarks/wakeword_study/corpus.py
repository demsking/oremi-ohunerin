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
"""Build the wake-word evaluation corpus used by the reliability study.

The corpus is written to '.tmp/wakeword_study' (gitignored scratch space) and
described by a JSON manifest. Nothing here is committed: every clip is either
synthesized locally with espeak-ng / flite or extracted from a public corpus
downloaded by fetch_sources().

Design constraints, all of them deliberate:

* **Base clips stay clean.** Positives and TTS negatives are synthesized once at
  16 kHz and stored untouched; noisy variants are derived from them so the
  sample-rate and threshold comparisons always see the same underlying speech.
* **Mixing is deterministic.** Noise is selected by sorted filename and mixed
  with a fixed per-sample seed, so re-running the builder reproduces byte
  identical variants.
* **The speech/noise ratio is documented.** RMS is measured over the whole clip,
  the noise is scaled to the requested SNR, and the measured SNR is recorded
  after mixing (peak normalisation preserves the ratio; nothing is clipped).
* **Human speech is real, the wake word is not.** No public corpus contains the
  invented wake word "oremi" spoken by a human, so positives are TTS. Real human
  speech is used for negatives, near-homophones and babble, which is where it
  matters most for false positives.
"""
import argparse
import csv
import hashlib
import json
import math
import random
import re
import shutil
import subprocess
import zlib
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parents[2]
CORPUS_DIR = BASE_DIR / '.tmp' / 'corpus'
STUDY_DIR = BASE_DIR / '.tmp' / 'wakeword_study'
RAW_DIR = STUDY_DIR / 'raw'
MANIFEST = STUDY_DIR / 'manifest.json'

SAMPLE_RATE = 16000
#: Anti-alias cutoff used by the candidate production downsampler, in hertz.
#: Kept below the 3 700 Hz upper mel filter of the French model.
DOWNSAMPLE_CUTOFF_HZ = 3700.0

# LibriSpeech dev-clean (CC BY 4.0), 40 real English speakers, 16 kHz FLAC.
LIBRISPEECH = CORPUS_DIR / 'ls' / 'LibriSpeech' / 'dev-clean'
# ESC-50 (CC BY-NC 3.0), 2 000 real 5 s environmental recordings at 44.1 kHz.
ESC50 = CORPUS_DIR / 'esc' / 'ESC-50-master'
# African Accented French (CC BY-SA 4.0), real French speakers, 16 kHz WAV.
AFF = CORPUS_DIR / 'aff' / 'African_Accented_French'

#: ESC-50 categories mapped onto the acoustic environments the study must cover.
ESC50_CATEGORIES = {
  'fan_ac': ['vacuum_cleaner', 'washing_machine'],
  'engine': ['engine', 'helicopter'],
  'keyboard_office': ['keyboard_typing', 'mouse_click'],
  'street_traffic': ['car_horn', 'siren', 'train'],
  'kitchen_home': ['pouring_water', 'drinking_sipping', 'can_opening'],
  'crying_child': ['crying_baby', 'laughing'],
  'weather': ['rain', 'wind', 'thunderstorm'],
  'clock_footsteps': ['clock_tick', 'footsteps', 'door_wood_knock'],
}

#: espeak-ng voices (prefix + variant). Variants are the documented +f/+m forms.
ESPEAK_VOICES = {
  'fr': ['fr', 'fr+f1', 'fr+f2', 'fr+f3', 'fr+m1', 'fr+m2', 'fr+m3', 'fr-be', 'fr-ch'],
  'en': ['en-us', 'en-us+f1', 'en-us+f2', 'en-us+f3', 'en-us+m1', 'en-us+m2', 'en-us+m3', 'en-gb', 'en-gb-x-rp'],
}

#: flite voices, English only (flite ships no French voice here).
FLITE_VOICES = ['kal', 'awb', 'rms', 'slt', 'kal16']

#: Positives, keyed by (language, engine), chosen from espeak-ng's own phoneme
#: output (`espeak-ng -q -x`) so that the synthetic voice actually says the wake
#: word instead of a look-alike:
#:
#:   fr  "oremi"    -> orm'i        (/ɔʁmi/, the /e/ is elided: NOT the wake word)
#:   fr  "au rémi"  -> o rem'i      (/o ʁemi/ = the configured "au rr ei mm ii")
#:   fr  "ô Rémi"   -> 'o: rem'i
#:   fr  "eau rémi" -> 'o rem'i
#:   en  "oremi"    -> 'o@mi        (/oʊəmi/, the /r/ is missing under espeak-ng)
#:   en  "oh remi"  -> 'oU r@m'i:   (/oʊ rəmi/, close to OW R EH M IY)
#:
#: flite is the other way round: the committed English fixture is flite "oremi"
#: and the project regression test relies on it.
POSITIVE_PHRASES = {
  ('fr', 'espeak-ng'): ['au rémi', 'ô Rémi', 'eau rémi', 'haut rémi', 'au rémi!'],
  ('en', 'espeak-ng'): ['oh remi', 'oh remi please', 'okay oh remi', 'hey oh remi'],
  ('en', 'flite'): ['oremi', 'ok oremi', 'hey oremi', 'oremi please'],
}

#: Literal brand spelling. Reported separately because espeak-ng renders it as a
#: different word in both languages (see above); it is still what a user typing
#: the product name would see, so it is measured but not folded into the primary
#: true-positive rate.
LITERAL_PHRASES = {
  'fr': ['oremi', 'ok oremi', 'dis oremi'],
  'en': ['oremi', 'ok oremi', 'hey oremi'],
}

#: Prefixes and suffixes that must NOT match the wake word. Exact homophones of
#: the configured pronunciation ("au rémi", "orémie", "oh remi") are deliberately
#: absent: those are the wake word, not near misses.
NEAR_HOMOPHONE_PHRASES = {
  'fr': ['rémi', 'remy', 'rémige', 'orémus', 'remix', 'harem', 'arôme', 'horaires'],
  'en': ['remy', 'aurora', 'harmony', 'remember', 'emory', 'jeremy', 'oregano', 'aroma', 'oreo', 'oregon'],
}

SIMILAR_NAME_PHRASES = {
  'fr': ['Aurélie', 'Amélie', 'Émilie', 'Jérémy', 'Roméo', 'Omar', 'Harmonie', 'orénoque', 'auréole', 'oreille'],
  'en': ['aurelie', 'amelia', 'emily', 'jeremy smith', 'romeo', 'omar', 'harmonica', 'mariah', 'mary', 'homer'],
}

PARTIAL_PHRASES = {
  'fr': ['ore', 'orem', 'oré'],
  'en': ['ore', 'orem', 'remi', 'oh re'],
}

UNRELATED_PHRASES = {
  'fr': [
    'bonjour', 'allume la lumière', 'quelle heure est-il', 'je vais bien merci', 'ouvre la porte',
    'mets la musique', 'il fait beau aujourd hui', "j'aimerais un café", 'combien ça coûte',
    'parle plus lentement', 'où est la gare', 'le temps est pluvieux', 'nous partons demain matin',
    'raconte-moi une histoire', 'le dîner est prêt', 'ferme la fenêtre', 'appelle-moi ce soir',
    'la réunion commence bientôt', 'j ai oublié mes clés', 'bonne nuit',
  ],
  'en': [
    'good morning', 'turn on the light', 'what time is it', 'i am fine thank you', 'open the door',
    'play some music', 'the weather is nice today', 'i would like a coffee', 'how much does it cost',
    'please speak more slowly', 'where is the train station', 'it is raining outside', 'we leave tomorrow morning',
    'tell me a story', 'dinner is ready', 'close the window', 'call me tonight', 'the meeting starts soon',
    'i forgot my keys', 'good night',
  ],
}


def run(cmd: list[str]) -> None:
  """Run a subprocess, raising with captured output on failure."""
  result = subprocess.run(cmd, capture_output=True, text=True)

  if result.returncode != 0:
    raise RuntimeError(f'command failed ({result.returncode}): {" ".join(cmd)}\n{result.stderr[-2000:]}')


def sha256_file(path: Path) -> str:
  """Return the SHA-256 hex digest of a file."""
  digest = hashlib.sha256()

  with path.open('rb') as file:
    for block in iter(lambda: file.read(1 << 20), b''):
      digest.update(block)

  return digest.hexdigest()


# --- audio primitives ---------------------------------------------------------

def decode_to_float(path: Path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
  """Decode any audio file to mono float64 [-1, 1] at sample_rate via ffmpeg."""
  result = subprocess.run(
    ['ffmpeg', '-v', 'error', '-i', str(path), '-ac', '1', '-ar', str(sample_rate), '-f', 's16le', '-'],
    capture_output=True,
  )

  if result.returncode != 0:
    raise RuntimeError(f'ffmpeg failed on {path}: {result.stderr.decode()[-500:]}')

  return np.frombuffer(result.stdout, dtype='<i2').astype(np.float64) / 32768.0


def encode_raw(samples: np.ndarray) -> bytes:
  """Convert float samples in [-1, 1] to little-endian signed 16-bit PCM bytes."""
  clipped = np.clip(samples, -1.0, 1.0)

  return (np.round(clipped * 32767.0)).astype('<i2').tobytes()


def decode_raw(data: bytes) -> np.ndarray:
  """Convert little-endian signed 16-bit PCM bytes to float64."""
  return np.frombuffer(data, dtype='<i2').astype(np.float64) / 32768.0


def rms(samples: np.ndarray) -> float:
  """Root-mean-square level of a float signal."""
  if samples.size == 0:
    return 0.0

  return float(np.sqrt(np.mean(np.square(samples))))


def lowpass_fir(cutoff_hz: float, sample_rate: int, numtaps: int = 129) -> np.ndarray:
  """Windowed-sinc low-pass FIR (Kaiser beta 10), DC gain 1."""
  taps = np.arange(numtaps) - (numtaps - 1) / 2.0
  kernel = np.sinc(2.0 * cutoff_hz / sample_rate * taps) * np.kaiser(numtaps, 10.0)

  return kernel / kernel.sum()


def downsample2(samples: np.ndarray, cutoff_hz: float = DOWNSAMPLE_CUTOFF_HZ, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
  """Anti-aliased 2:1 decimation (16 kHz -> 8 kHz) using a linear-phase FIR.

  The group delay is compensated so the output stays time-aligned with the
  input; the result is exactly half as long as the input.
  """
  taps = lowpass_fir(cutoff_hz, sample_rate)
  filtered = np.convolve(samples, taps, mode='full')
  delay = (len(taps) - 1) // 2
  aligned = filtered[delay:delay + len(samples)]

  return aligned[::2]


def upsample2(samples: np.ndarray, sample_rate: int = 8000) -> np.ndarray:
  """2:1 interpolation (8 kHz -> 16 kHz) with a windowed-sinc FIR, gain 2."""
  taps = lowpass_fir(sample_rate * 0.45, sample_rate * 2)
  zeros = np.zeros(len(samples) * 2, dtype=np.float64)
  zeros[::2] = samples

  return np.convolve(zeros, taps * 2.0, mode='same')


def ffmpeg_resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
  """Resample with ffmpeg's soxr engine, used as an independent quality reference."""
  proc = subprocess.run(
    ['ffmpeg', '-v', 'error', '-f', 's16le', '-ar', str(src_rate), '-ac', '1', '-i', 'pipe:0',
     '-af', 'aresample=resampler=soxr:precision=28', '-f', 's16le', '-ar', str(dst_rate), '-ac', '1', 'pipe:1'],
    input=encode_raw(samples), capture_output=True,
  )

  if proc.returncode != 0:
    raise RuntimeError(f'ffmpeg resample failed: {proc.stderr.decode()[-500:]}')

  return decode_raw(proc.stdout)


def room_simulate(samples: np.ndarray, seed: int, decay_ms: float = 220.0, wet: float = 0.35) -> np.ndarray:
  """Simulate a mildly reverberant, slightly distant pickup with a synthetic RIR.

  Recorded far-field wake words were not available for this study, so the
  "distant" condition is explicitly synthetic: an exponentially decaying
  Gaussian impulse response convolved with the dry signal, then attenuated.
  """
  rng = np.random.default_rng(seed)
  length = int(SAMPLE_RATE * decay_ms / 1000.0)
  rir = rng.normal(0.0, 1.0, length) * np.exp(-np.arange(length) / (SAMPLE_RATE * 0.06))
  rir[0] = 1.0
  rir /= math.sqrt(float(np.sum(np.square(rir))))
  wet_signal = np.convolve(samples, rir, mode='full')[:len(samples)]
  mixed = (1.0 - wet) * samples + wet * wet_signal

  return mixed * (10 ** (-12.0 / 20.0))


def mix_at_snr(speech: np.ndarray, noise: np.ndarray, snr_db: float, seed: int) -> tuple[np.ndarray, float]:
  """Add noise to speech at the requested SNR.

  Returns the mixed signal and the measured SNR in dB. The noise is tiled to the
  speech length starting at a seeded random offset; the mix is scaled down (never
  clipped) if it would exceed full scale, which preserves the ratio.
  """
  rng = np.random.default_rng(seed)

  if len(noise) >= len(speech):
    start = int(rng.integers(0, len(noise) - len(speech) + 1))
    fitted = noise[start:start + len(speech)]
  else:
    repeats = int(math.ceil(len(speech) / len(noise)))
    fitted = np.tile(noise, repeats)[:len(speech)]

  speech_rms = rms(speech)
  noise_rms = rms(fitted)

  if noise_rms <= 0.0 or speech_rms <= 0.0:
    return speech.copy(), float('inf')

  gain = speech_rms / noise_rms * (10 ** (-snr_db / 20.0))
  scaled_noise = fitted * gain
  mixed = speech + scaled_noise
  peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0

  if peak > 0.99:
    mixed = mixed * (0.99 / peak)

  measured = 20.0 * math.log10(max(rms(speech), 1e-12) / max(rms(scaled_noise), 1e-12))

  return mixed, measured


# --- sources ------------------------------------------------------------------

def fetch_sources() -> None:
  """Download and extract the three public corpora (idempotent)."""
  CORPUS_DIR.mkdir(parents=True, exist_ok=True)
  jobs = [
    ('dev-clean.tar.gz', 'https://www.openslr.org/resources/12/dev-clean.tar.gz', 'ls'),
    ('esc50.zip', 'https://github.com/karolpiczak/ESC-50/archive/refs/heads/master.zip', 'esc'),
    ('aff.tar.gz', 'https://openslr.trmal.net/resources/57/African_Accented_French.tar.gz', 'aff'),
  ]

  for name, url, marker in jobs:
    target = CORPUS_DIR / marker

    if (target / '.complete').exists():
      continue

    archive = CORPUS_DIR / name

    if not archive.exists():
      print(f'downloading {url}', flush=True)
      run(['curl', '-sS', '-L', '-o', str(archive), url])

    target.mkdir(parents=True, exist_ok=True)
    print(f'extracting {name}', flush=True)

    if name.endswith('.zip'):
      run(['unzip', '-q', '-o', str(archive), '-d', str(target)])
    else:
      run(['tar', 'xzf', str(archive), '-C', str(target)])

    archive.unlink()
    (target / '.complete').write_text('ok\n', encoding='utf-8')


# --- TTS base clips -----------------------------------------------------------

SPEAKER_NOTE = 'synthetic voice, not a human speaker'


def synth_espeak(voice: str, text: str, wpm: int, pitch: int, amp: int, out: Path) -> bool:
  """Synthesize one phrase with espeak-ng; returns False when the voice is unavailable."""
  result = subprocess.run(
    ['espeak-ng', '-v', voice, '-s', str(wpm), '-p', str(pitch), '-a', str(amp), '-w', str(out), text],
    capture_output=True,
  )

  return result.returncode == 0 and out.exists() and out.stat().st_size > 0


def synth_flite(voice: str, text: str, out: Path) -> bool:
  """Synthesize one phrase with flite; returns False when the voice is unavailable."""
  result = subprocess.run(['flite', '-voice', voice, '-t', text, '-o', str(out)], capture_output=True)

  return result.returncode == 0 and out.exists() and out.stat().st_size > 0


def apply_level(samples: np.ndarray, level: str, seed: int) -> np.ndarray:
  """Apply one of the documented level/distance conditions to a clean clip."""
  if level == 'normal':
    return samples

  if level == 'quiet':
    return samples * (10 ** (-20.0 / 20.0))

  if level == 'loud':
    peak = float(np.max(np.abs(samples))) or 1.0
    return samples / peak * 0.94

  if level == 'distant':
    return room_simulate(samples, seed)

  raise ValueError(f'unknown level {level!r}')


def tts_positive_specs(language: str) -> list[dict]:
  """Deterministic positive specifications: voices x speeds x levels x phrases."""
  specs: list[dict] = []
  voices = list(ESPEAK_VOICES[language]) + (FLITE_VOICES if language == 'en' else [])
  speeds = [100, 135, 175]
  levels = ['normal', 'quiet']
  index = 0

  for voice in voices:
    engine = 'flite' if voice in FLITE_VOICES else 'espeak-ng'
    phrases = POSITIVE_PHRASES.get((language, engine))

    if not phrases:
      continue

    for speed_index, wpm in enumerate(speeds):
      for level in levels:
        specs.append({
          'engine': engine,
          'voice': voice,
          'text': phrases[(index + speed_index) % len(phrases)],
          'wpm': wpm,
          'pitch': [30, 50, 70][speed_index],
          'amp': 150,
          'level': level,
          'label': 'wakeword',
        })
        index += 1

  for voice in voices[:6]:
    engine = 'flite' if voice in FLITE_VOICES else 'espeak-ng'
    phrases = POSITIVE_PHRASES.get((language, engine))

    if not phrases:
      continue

    specs.append({
      'engine': engine, 'voice': voice, 'text': phrases[0], 'wpm': 135, 'pitch': 50,
      'amp': 150, 'level': 'distant', 'label': 'wakeword',
    })
    specs.append({
      'engine': engine, 'voice': voice, 'text': phrases[0], 'wpm': 110, 'pitch': 40,
      'amp': 200, 'level': 'loud', 'label': 'wakeword',
    })

  # Literal brand spelling, espeak-ng only, reported as its own label.
  for phrase_index, text in enumerate(LITERAL_PHRASES[language]):
    for voice_index, voice in enumerate(ESPEAK_VOICES[language][:6]):
      specs.append({
        'engine': 'espeak-ng', 'voice': voice, 'text': text,
        'wpm': [110, 135, 160][voice_index % 3], 'pitch': 50, 'amp': 150,
        'level': 'normal', 'label': 'wakeword_literal',
      })

  return specs


def tts_negative_specs(language: str) -> list[dict]:
  """Deterministic negative specifications: near-homophones, names, partials, phrases."""
  specs: list[dict] = []
  voices = list(ESPEAK_VOICES[language]) + (FLITE_VOICES if language == 'en' else [])
  groups = [
    ('near_homophone', NEAR_HOMOPHONE_PHRASES[language]),
    ('similar_name', SIMILAR_NAME_PHRASES[language]),
    ('partial', PARTIAL_PHRASES[language]),
    ('unrelated', UNRELATED_PHRASES[language]),
  ]

  for group_index, (kind, phrases) in enumerate(groups):
    for phrase_index, text in enumerate(phrases):
      for variant in range(2):
        voice = voices[(group_index * 3 + phrase_index + variant) % len(voices)]
        specs.append({
          'engine': 'flite' if voice in FLITE_VOICES else 'espeak-ng',
          'voice': voice,
          'text': text,
          'wpm': [110, 135, 160][variant],
          'pitch': [45, 55][variant],
          'amp': 150,
          'level': 'normal',
          'kind': kind,
        })

  return specs


# --- corpus assembly ----------------------------------------------------------

def write_raw(relative: str, samples: np.ndarray) -> dict:
  """Write a float clip as 16 kHz s16le PCM and return its file metadata."""
  path = RAW_DIR / relative
  path.parent.mkdir(parents=True, exist_ok=True)
  payload = encode_raw(samples)
  path.write_bytes(payload)

  return {
    'path': str(path.relative_to(STUDY_DIR)),
    'duration_s': round(len(samples) / SAMPLE_RATE, 4),
    'bytes': len(payload),
    'sha256': hashlib.sha256(payload).hexdigest()[:16],
  }


def trim_speech(samples: np.ndarray, max_seconds: float = 4.0, min_seconds: float = 0.6) -> np.ndarray | None:
  """Trim long recordings and drop clips that are too short for a fair comparison."""
  limit = int(max_seconds * SAMPLE_RATE)

  if len(samples) > limit:
    samples = samples[:limit]

  if len(samples) < int(min_seconds * SAMPLE_RATE):
    return None

  return samples


def build_tts_bases() -> list[dict]:
  """Synthesize the clean TTS base clips (positives and negatives)."""
  samples: list[dict] = []
  tmp = STUDY_DIR / 'tts_tmp'
  tmp.mkdir(parents=True, exist_ok=True)
  seed = 20260601

  for language in ('fr', 'en'):
    for index, spec in enumerate(tts_positive_specs(language)):
      wav = tmp / 'pos.wav'

      if spec['engine'] == 'flite':
        ok = synth_flite(spec['voice'], spec['text'], wav)
      else:
        ok = synth_espeak(spec['voice'], spec['text'], spec['wpm'], spec['pitch'], spec['amp'], wav)

      if not ok:
        print(f'  skip unavailable voice {spec["voice"]}', flush=True)
        continue

      audio = decode_to_float(wav)
      audio = apply_level(audio, spec['level'], seed + index)
      meta = write_raw(f'base/tts-{language}-pos-{index:03d}.raw', audio)
      samples.append({
        'id': f'tts-{language}-pos-{index:03d}', 'language': language, 'kind': 'positive', 'label': spec['label'],
        'text': spec['text'], 'engine': spec['engine'], 'voice': spec['voice'], 'speaker': None,
        'speed_wpm': spec['wpm'], 'pitch': spec['pitch'], 'level': spec['level'],
        'noise': None, 'snr_db': None, 'noise_measured_snr_db': None,
        'provenance': f'espeak-ng/flite TTS, voice {spec["voice"]}, {SPEAKER_NOTE}',
        **meta,
      })

    for index, spec in enumerate(tts_negative_specs(language)):
      wav = tmp / 'neg.wav'

      if spec['engine'] == 'flite':
        ok = synth_flite(spec['voice'], spec['text'], wav)
      else:
        ok = synth_espeak(spec['voice'], spec['text'], spec['wpm'], spec['pitch'], spec['amp'], wav)

      if not ok:
        continue

      audio = apply_level(decode_to_float(wav), spec['level'], seed + 5000 + index)
      meta = write_raw(f'base/tts-{language}-neg-{index:03d}.raw', audio)
      samples.append({
        'id': f'tts-{language}-neg-{index:03d}', 'language': language, 'kind': 'negative', 'label': spec['kind'],
        'text': spec['text'], 'engine': spec['engine'], 'voice': spec['voice'], 'speaker': None,
        'speed_wpm': spec['wpm'], 'pitch': spec['pitch'], 'level': 'normal',
        'noise': None, 'snr_db': None, 'noise_measured_snr_db': None,
        'provenance': f'espeak-ng/flite TTS, voice {spec["voice"]}, {SPEAKER_NOTE}',
        **meta,
      })

  shutil.rmtree(tmp, ignore_errors=True)

  return samples


def librispeech_index() -> list[tuple[str, str, Path]]:
  """Return (utterance id, uppercase transcript, flac path) for LibriSpeech dev-clean."""
  entries: list[tuple[str, str, Path]] = []

  for transcript in sorted(LIBRISPEECH.rglob('*.trans.txt')):
    for line in transcript.read_text(encoding='utf-8').splitlines():
      utterance, _, text = line.partition(' ')
      flac = transcript.parent / f'{utterance}.flac'

      if flac.exists():
        entries.append((utterance, text, flac))

  return entries


def aff_index() -> list[tuple[str, str, Path]]:
  """Return (utterance id, transcript, wav path) for the African Accented French set."""
  prompts: dict[str, str] = {}

  for transcript in sorted((AFF / 'transcripts').rglob('*.txt')):
    for line in transcript.read_text(encoding='utf-8', errors='replace').splitlines():
      key, _, text = line.partition(' ')

      if key and text:
        prompts[key] = text

  entries: list[tuple[str, str, Path]] = []

  for wav in sorted((AFF / 'speech').rglob('*.wav')):
    utterance = wav.stem
    entries.append((utterance, prompts.get(utterance, ''), wav))

  return entries


def build_real_human() -> tuple[list[dict], dict[str, list[dict]]]:
  """Select real human recordings: negatives, near-homophone hits and babble donors."""
  rng = random.Random(20260602)
  samples: list[dict] = []
  donors: dict[str, list[dict]] = {'en': [], 'fr': []}

  index_en = librispeech_index()
  index_fr = aff_index()
  near_words_en = ['remy', 'remi', 'aurora', 'harmony', 'emory', 'jeremy', 'remember', 'oregon', 'oreo', 'aroma']
  near_words_fr = ['remi', 'remy', 'rémi']

  picks: list[tuple[str, str, str, Path]] = []
  chosen_en = rng.sample([e for e in index_en if e[2].stat().st_size > 20000], 40)

  for utterance, text, path in chosen_en:
    picks.append(('en', 'real_human_unrelated', text, path))

  near_en = 0

  for utterance, text, path in index_en:
    words = set(re.findall(r"[a-z']+", text.lower()))

    if words & set(near_words_en) and near_en < 12:
      picks.append(('en', 'real_human_near_homophone', text, path))
      near_en += 1

  chosen_fr = rng.sample([e for e in index_fr if e[2].stat().st_size > 20000 and len(e[1]) > 0], 40)

  for utterance, text, path in chosen_fr:
    picks.append(('fr', 'real_human_unrelated', text, path))

  near_fr = 0

  for utterance, text, path in index_fr:
    lowered = text.lower()

    if any(word in lowered for word in near_words_fr) and near_fr < 12:
      picks.append(('fr', 'real_human_near_homophone', text, path))
      near_fr += 1

  seen_text: set[str] = set()

  for order, (language, label, text, path) in enumerate(picks):
    if text in seen_text:
      continue

    seen_text.add(text)

    audio = decode_to_float(path)
    audio = trim_speech(audio)

    if audio is None:
      continue

    sample_id = f'real-{language}-{label.split("_")[-1]}-{order:03d}'
    meta = write_raw(f'base/{sample_id}.raw', audio)
    samples.append({
      'id': sample_id, 'language': language, 'kind': 'negative', 'label': label, 'text': text,
      'engine': 'human', 'voice': None, 'speaker': path.parent.parent.name if language == 'en' else path.parent.name,
      'speed_wpm': None, 'pitch': None, 'level': 'natural', 'noise': None, 'snr_db': None,
      'noise_measured_snr_db': None,
      'provenance': ('LibriSpeech dev-clean (CC BY 4.0)' if language == 'en' else 'African Accented French, OpenSLR SLR57 (CC BY-SA 4.0)') + f', {path.name}',
      **meta,
    })

  # Babble donors: six real speakers per language, reused to build multi-talker noise.
  for language, source in (('en', chosen_en), ('fr', chosen_fr)):
    for utterance, text, path in source[:6]:
      audio = trim_speech(decode_to_float(path), max_seconds=4.0)

      if audio is None:
        continue

      donors[language].append({'speaker': utterance, 'samples': audio})

  return samples, donors


def esc50_files_by_category() -> dict[str, list[Path]]:
  """Map ESC-50 categories to their audio files using the shipped metadata CSV."""
  grouped: dict[str, list[Path]] = {}

  with (ESC50 / 'meta' / 'esc50.csv').open(encoding='utf-8') as file:
    for row in csv.DictReader(file):
      path = ESC50 / 'audio' / row['filename']

      if path.exists():
        grouped.setdefault(row['category'], []).append(path)

  return {key: sorted(value) for key, value in grouped.items()}


def build_noises() -> dict[str, np.ndarray]:
  """Extract real ESC-50 noise and synthesize white/pink/brown references."""
  noises: dict[str, np.ndarray] = {}
  rng = np.random.default_rng(20260603)
  by_category = esc50_files_by_category()

  for environment, categories in ESC50_CATEGORIES.items():
    chunks: list[np.ndarray] = []

    for category in categories:
      files = by_category.get(category, [])[:2]

      for path in files:
        audio = decode_to_float(path)
        chunks.append(audio[:SAMPLE_RATE * 5] if len(audio) > SAMPLE_RATE * 5 else audio)

    if chunks:
      noises[environment] = np.concatenate(chunks)

  duration = SAMPLE_RATE * 20
  white = rng.normal(0.0, 0.25, duration)
  spectrum = np.fft.rfft(white)
  frequencies = np.fft.rfftfreq(duration, d=1.0 / SAMPLE_RATE)
  frequencies[0] = frequencies[1]
  pink = np.fft.irfft(spectrum / np.sqrt(frequencies), n=duration)
  brown = np.cumsum(rng.normal(0.0, 1.0, duration))
  brown = brown - np.linspace(brown[0], brown[-1], duration)
  noises['white'] = white / (np.max(np.abs(white)) or 1.0) * 0.7
  noises['pink'] = pink / (np.max(np.abs(pink)) or 1.0) * 0.7
  noises['brown'] = brown / (np.max(np.abs(brown)) or 1.0) * 0.7

  return noises


def build_babble(donors: dict[str, list[dict]]) -> dict[str, np.ndarray]:
  """Build multi-talker babble from real human recordings, one mix per language."""
  babble: dict[str, np.ndarray] = {}

  for language, speakers in donors.items():
    if len(speakers) < 3:
      continue

    length = int(SAMPLE_RATE * 8)
    mixed = np.zeros(length)

    for speaker in speakers:
      clip = speaker['samples']
      repeats = int(math.ceil(length / len(clip)))
      tiled = np.tile(clip, repeats)[:length]
      level = rms(tiled) or 1.0
      mixed += tiled / level

    mixed = mixed / (np.max(np.abs(mixed)) or 1.0) * 0.7
    babble[language] = mixed

  return babble


def build_mixed(samples: list[dict], noises: dict[str, np.ndarray], babble: dict[str, np.ndarray], per_language: int = 8) -> list[dict]:
  """Derive noisy variants from clean bases, at documented SNRs."""
  mixed: list[dict] = []
  rng = random.Random(20260605)
  noise_names = ['fan_ac', 'keyboard_office', 'street_traffic', 'kitchen_home', 'weather', 'white', 'pink', 'babble']
  snrs = [20.0, 10.0, 5.0]

  for language in ('fr', 'en'):
    positives = [s for s in samples if s['language'] == language and s['kind'] == 'positive' and s['level'] == 'normal']
    negatives = [s for s in samples if s['language'] == language and s['kind'] == 'negative' and 'real' not in s['id']]
    rng.shuffle(positives)
    rng.shuffle(negatives)

    for group, bases in (('pos', positives[:per_language]), ('neg', negatives[:per_language])):
      for base in bases:
        speech = decode_raw((STUDY_DIR / base['path']).read_bytes())

        for noise_name in noise_names:
          if noise_name == 'babble':
            noise = babble.get(language)

            if noise is None:
              continue
          else:
            noise = noises.get(noise_name)

          if noise is None:
            continue

          for snr in snrs:
            seed = zlib.crc32(f'{base["id"]}|{noise_name}|{snr}|{language}'.encode())
            blended, measured = mix_at_snr(speech, noise, snr, seed)
            sample_id = f'mix-{base["id"]}-{noise_name}-{int(snr)}'
            meta = write_raw(f'mix/{sample_id}.raw', blended)
            mixed.append({
              **{k: v for k, v in base.items() if k not in ('path', 'duration_s', 'bytes', 'sha256')},
              'id': sample_id, 'kind': base['kind'], 'label': base['label'] if base['kind'] == 'negative' else 'wakeword',
              'base_id': base['id'], 'noise': noise_name, 'snr_db': snr, 'noise_measured_snr_db': round(measured, 2),
              'provenance': f'{base["provenance"]}; mixed with {noise_name} noise at {int(snr)} dB SNR',
              **meta,
            })

  return mixed


def build(limit: int | None = None) -> dict:
  """Build every phase and write the manifest."""
  for directory in (RAW_DIR, STUDY_DIR):
    directory.mkdir(parents=True, exist_ok=True)

  print('synthesizing TTS bases', flush=True)
  samples = build_tts_bases()
  print('selecting real human recordings', flush=True)
  real, donors = build_real_human()
  samples.extend(real)
  print('extracting noise', flush=True)
  noises = build_noises()
  babble = build_babble(donors)
  print(f'mixing noisy variants (babble for {sorted(babble)})', flush=True)
  samples.extend(build_mixed(samples, noises, babble))

  if limit:
    samples = samples[:limit]

  manifest = {
    'sample_rate': SAMPLE_RATE,
    'downsample_cutoff_hz': DOWNSAMPLE_CUTOFF_HZ,
    'sources': {
      'LibriSpeech dev-clean': 'https://www.openslr.org/resources/12/dev-clean.tar.gz (CC BY 4.0)',
      'ESC-50': 'https://github.com/karolpiczak/ESC-50 (CC BY-NC 3.0)',
      'African Accented French': 'https://www.openslr.org/57/ (CC BY-SA 4.0)',
      'TTS': 'espeak-ng 1.5x and flite 2.2 (local synthesis)',
    },
    'counts': {
      'positive': sum(1 for s in samples if s['kind'] == 'positive'),
      'negative': sum(1 for s in samples if s['kind'] == 'negative'),
      'human': sum(1 for s in samples if s['engine'] == 'human'),
      'noisy': sum(1 for s in samples if s['noise']),
    },
    'samples': samples,
  }
  MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
  print(json.dumps(manifest['counts'], indent=1))

  return manifest


def main() -> None:
  parser = argparse.ArgumentParser(description='Build the wake-word reliability study corpus.')
  parser.add_argument('--no-fetch', action='store_true', help='skip corpus download')
  parser.add_argument('--limit', type=int, default=None, help='keep only the first N samples (smoke tests)')
  args = parser.parse_args()

  if not args.no_fetch:
    fetch_sources()

  build(limit=args.limit)


if __name__ == '__main__':
  main()
