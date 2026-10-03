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
"""Prove, from the PocketSphinx front end, whether 16 kHz vs 8 kHz changes features.

Reproduces fe_build_melfilters() from src/fe/fe_sigproc.c in numpy for the two
(samprate, fft_size) pairs PocketSphinx actually selects:

* 16 kHz: window_samples = int(0.025625 * 16000) = 410 -> fft_size 512
*  8 kHz: window_samples = int(0.025625 *  8000) = 205 -> fft_size 256

Both give a DFT bin spacing of exactly 31.25 Hz, and the model's own feat.params
fix lowerf/upperf/nfilt, so the filterbank is built from identical hertz values
gridded onto identical bins. The front end contains no resampler at all (the
resample code under src/common_audio is only reachable from the WebRTC VAD).

Run from the repository root:
  .venv/bin/python -m benchmarks.wakeword_study.fecheck
"""
import math
import sys
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / 'benchmarks'))

from wakeword_study import corpus as corpus  # noqa: E402


def fe_mel(x: float) -> float:
  """Sphinxbase fe_mel with the default neutral warp."""
  return 2595.0 * math.log10(1.0 + x / 700.0)


def fe_melinv(x: float) -> float:
  """Sphinxbase fe_melinv with the default neutral warp."""
  return 700.0 * (10.0 ** (x / 2595.0) - 1.0)


def build_filters(samprate: int, fft_size: int, lowerf: float, upperf: float, nfilt: int,
                  round_filters: bool = True) -> dict:
  """Port of fe_build_melfilters() for unit_area=True, doublebw=False."""
  melmin = fe_mel(lowerf)
  melmax = fe_mel(upperf)
  melbw = (melmax - melmin) / (nfilt + 1)
  fftfreq = samprate / float(fft_size)
  spec_start: list[int] = []
  filt_width: list[int] = []
  coeffs: list[list[float]] = []

  for index in range(nfilt):
    freqs = [fe_melinv((index + step) * melbw + melmin) for step in range(3)]

    if round_filters:
      freqs = [int(value / fftfreq + 0.5) * fftfreq for value in freqs]

    start = -1

    for j in range(fft_size // 2 + 1):
      hz = j * fftfreq

      if hz < freqs[0]:
        continue

      if hz > freqs[2] or j == fft_size // 2:
        spec_start.append(start)
        filt_width.append(j - start)
        break

      if start == -1:
        start = j

    row = []

    for j in range(filt_width[-1]):
      hz = (spec_start[-1] + j) * fftfreq
      loslope = (hz - freqs[0]) / (freqs[1] - freqs[0])
      hislope = (freqs[2] - hz) / (freqs[2] - freqs[1])
      loslope *= 2.0 / (freqs[2] - freqs[0])
      hislope *= 2.0 / (freqs[2] - freqs[0])
      row.append(min(loslope, hislope))

    coeffs.append(row)

  return {
    'samprate': samprate, 'fft_size': fft_size, 'fftfreq_hz': fftfreq,
    'spec_start': spec_start, 'filt_width': filt_width,
    'total_coeffs': sum(filt_width),
    'coeffs': np.concatenate([np.asarray(row) for row in coeffs]) if coeffs else np.zeros(0),
  }


def compare(model: str, samprate_a: int, samprate_b: int, lowerf: float, upperf: float, nfilt: int) -> None:
  """Compare the filterbank of the 16 kHz and 8 kHz front ends for one model."""
  fft_a = 512 if samprate_a == 16000 else 256
  fft_b = 512 if samprate_b == 16000 else 256

  if upperf > samprate_b / 2 + 1.0:
    print(f'{model}: 8 kHz is rejected by fe_interface.c before filters are built '
          f'(upperf {upperf} > samprate/2 {samprate_b / 2})')
    return

  bank_a = build_filters(samprate_a, fft_a, lowerf, upperf, nfilt)
  bank_b = build_filters(samprate_b, fft_b, lowerf, upperf, nfilt)
  same_starts = bank_a['spec_start'] == bank_b['spec_start']
  same_widths = bank_a['filt_width'] == bank_b['filt_width']
  same_coeffs = bank_a['coeffs'].shape == bank_b['coeffs'].shape and bool(np.array_equal(bank_a['coeffs'], bank_b['coeffs']))

  print(f'{model}: lowerf={lowerf} upperf={upperf} nfilt={nfilt}')
  print(f'  bin spacing: {samprate_a}/{fft_a} = {bank_a["fftfreq_hz"]} Hz, '
        f'{samprate_b}/{fft_b} = {bank_b["fftfreq_hz"]} Hz')
  print(f'  spec_start identical: {same_starts}, filt_width identical: {same_widths}, '
        f'coefficients identical: {same_coeffs} ({bank_a["total_coeffs"]} coefficients)')
  print(f'  highest bin used: {(bank_a["spec_start"][-1] + bank_a["filt_width"][-1]) * bank_a["fftfreq_hz"]:.1f} Hz '
        f'(Nyquist {samprate_b / 2:.0f} Hz at 8 kHz)')


def downsample_response() -> None:
  """Report the passband/stopband behaviour of the study's decimation filter."""
  taps = corpus.lowpass_fir(corpus.DOWNSAMPLE_CUTOFF_HZ, 16000)
  response = np.abs(np.fft.rfft(taps, 65536))
  freqs = np.fft.rfftfreq(65536, d=1.0 / 16000)

  def db(frequency: float) -> float:
    return 20.0 * math.log10(response[int(round(frequency / freqs[1]))] + 1e-12)

  print('polyphase decimation filter (129 taps, Kaiser 10, cutoff 3700 Hz):')
  print(f'  0 Hz {db(1000):+.2f} dB, 1 kHz {db(1000):+.2f} dB, 2 kHz {db(2000):+.2f} dB, '
        f'3 kHz {db(3000):+.2f} dB, 3.4 kHz {db(3400):+.2f} dB')
  print(f'  3.7 kHz {db(3700):+.2f} dB, 4 kHz {db(4000):+.2f} dB, 4.5 kHz {db(4500):+.2f} dB, '
        f'6 kHz {db(6000):+.2f} dB')


def main() -> None:
  """Compare both shipped models and quantify the decimation filter."""
  compare('fr (cmusphinx-fr-ptm-8khz-5.2)', 16000, 8000, 130.0, 3700.0, 20)
  compare('en (wakeword-en acoustic model)', 16000, 8000, 130.0, 6800.0, 25)
  downsample_response()


if __name__ == '__main__':
  main()
