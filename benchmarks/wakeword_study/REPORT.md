# Wake-word reliability study: French sample rate and kws_threshold

Measured with PocketSphinx 5.1.1 on the oremi-ohunerin working tree (a7f268e),
harness in benchmarks/wakeword_study/. Raw results: .tmp/wakeword_study/results.json,
tables: .tmp/wakeword_study/analysis.md. No production code was changed.

## Executive summary

Tested a 1,576-clip corpus: 582 positives (546 intended-pronunciation TTS + 36 literal
brand spelling) and 994 negatives (near-homophones, similar names, partial words,
unrelated phrases, real human speech from LibriSpeech dev-clean and African Accented
French, real ESC-50 environmental noise, white/pink noise, multi-talker babble), across
both shipped languages, at 1e-10 to 1e-30, with and without noise.

1. The French model is genuinely 8 kHz-trained (feat.params upperf 3700, lowerf 130,
   nfilt 20, no samprate line) and PocketSphinx runs it at its 16000 Hz default. Feeding
   16 kHz is nevertheless correct: the model's own feat.params band-limits analysis to
   3718.8 Hz, and the (16000, fft 512) and (8000, fft 256) front ends have the same
   31.25 Hz bin spacing, so the mel filterbank is identical (236 coefficients, verified
   by porting fe_build_melfilters to numpy). Explicit 8 kHz downsampling measured
   equal-or-worse at every threshold tested.
2. The English model cannot run at 8 kHz at all: its feat.params upperf is 6800 Hz and
   PocketSphinx aborts with Upper frequency 6800.0 is higher than samprate/2 (4000.0).
3. PocketSphinx does not resample. Feeding 16 kHz audio to an 8 kHz configuration, or
   8 kHz audio to a 16 kHz configuration, collapses the median French margin by 10-15
   orders of magnitude.
4. kws_threshold=1e-15 does not separate positives from negatives cleanly on this
   benchmark. Clean French positives fire at 8/66 (12.1%); clean real-human negatives
   never fire at 1e-15, but near-miss words do (18/312 of all French negatives, 5.8%),
   and 3/50 clean real-human English utterances do (6.0%, one of them at 1e-10).
5. Raising the threshold to 1e-10 halves the French true-positive rate; lowering it to
   1e-30 multiplies the French false-positive rate by 3.6 and the English one by 5.5.
   There is no dominant alternative operating point in the measured range.
6. Adding noise at 20/10/5 dB did not degrade detection: paired clean-vs-noisy showed
   noise only adding detections (7 French and 1 English base that missed clean fired
   under noise). This is consistent with the KWS margin accumulating phone-loop
   penalties over the frames since the last utterance reset, not with noise helping the
   acoustics.
7. Recommendation: keep the 16 kHz path and keep 1e-15. No production change is
   justified by the measurements.

## French sample-rate investigation

What the model is: models/wakeword-fr/cmusphinx-fr-ptm-8khz-5.2. Its feat.params (byte-
verified, 12 lines) sets lowerf 130, upperf 3700, nfilt 20, transform dct, lifter 22,
feat 1s_c_d_dd, svspec 0-12/13-25/26-38, agc none, cmn current, varnorm no, model ptm.
It has no samprate line. upperf 3700 against a 4000 Hz Nyquist and nfilt 20 are the
classic 8 kHz PTM geometry; the directory name agrees.

What PocketSphinx actually uses: ps_expand_model_config (src/pocketsphinx.c:105-131)
parses feat.params only for keys it contains, so samprate stays at the cmd_ln default of
16000. Decoder.get_config() on the real engine reports samprate=16000, lowerf=130.0,
upperf=3700.0, nfilt=20, ceplen=13, feat=1s_c_d_dd, transform=dct, wlen=0.025625.

Does PocketSphinx resample: no. fe_parse_general_params reads samprate directly and
fe_process_frames consumes raw samples; the resample code under src/common_audio is
reachable only from the WebRTC VAD (grep for resample across src/acmod.c, src/fe/*.c
and src/feat/*.c returns nothing). The mismatch controls confirm this empirically.

Filterbank equivalence (benchmarks/wakeword_study/fecheck.py): with round_filters=True,
unit_area=True, doublebw=False and a neutral warp (warp_params unset), the 16 kHz front
end (window_samples 410, fft 512) and the 8 kHz front end (window_samples 205, fft 256)
produce byte-identical spec_start, filt_width and coefficients - 236 coefficients, the
highest bin used is 3718.8 Hz, below both Nyquists. So 16 kHz feeding is not an
acoustic mismatch; the only difference between the two paths is what the decimation
filter does to the 0-3700 Hz band (the study filter is -0.04 dB at 3.4 kHz, -6.02 dB at
its 3.7 kHz cutoff, -46 dB at 4 kHz).

Benchmark methodology: the same 16 kHz source clips are pushed through five
configurations - A: 16 kHz source to PS samprate 16000 (production); B: high-quality
129-tap Kaiser polyphase decimation to 8 kHz to PS 8000; B2: ffmpeg/soxr decimation to
8 kHz to PS 8000 (independent resampler quality check); D: 16 kHz source to PS 8000;
E: 8 kHz source to PS 16000. Every configuration sees the same speech; chunking is
50 ms and 0.5 s of silence pads both ends. Threshold behaviour is measured with
production semantics (WakewordEngine.process_raw, including the reset on every
hypothesis) at 18 thresholds; the reset-free margin pass is used only for the
side-by-side score comparison, where all variants are treated identically.

Measured results (French, production semantics, 66 clean + 192 noisy primary positives,
312 negatives):

| Threshold | A TPR | B TPR | B2 TPR | A FPR | B FPR | B2 FPR |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1e-10 | 0.062 | 0.050 | 0.054 | 0.019 | 0.016 | 0.016 |
| 1e-12 | 0.089 | 0.078 | 0.081 | 0.032 | 0.038 | 0.035 |
| 1e-15 | 0.128 | 0.112 | 0.116 | 0.058 | 0.058 | 0.058 |
| 1e-17 | 0.143 | 0.140 | 0.136 | 0.064 | 0.071 | 0.071 |
| 1e-20 | 0.190 | 0.186 | 0.182 | 0.080 | 0.090 | 0.083 |
| 1e-25 | 0.264 | 0.260 | 0.267 | 0.119 | 0.122 | 0.122 |
| 1e-30 | 0.345 | 0.341 | 0.329 | 0.208 | 0.189 | 0.192 |

Reset-free median score (median log10 of the equivalent threshold; higher is better):
A -35.44 (clean) / -32.24 (noisy); B -37.13 / -32.69; B2 -37.27 / -33.09. A is 1.7 dex
ahead on clean speech and 0.5-0.9 dex ahead under noise. Mismatch controls: D -45.27,
E -50.52, i.e. 10-15 dex worse than A.

English behaves differently: variants B and B2 cannot even be constructed
(RuntimeError: Failed to initialize PocketSphinx, preceded by fe_interface.c: Upper
frequency 6800.0 is higher than samprate/2 (4000.0)). The English path has no legal
8 kHz configuration with its shipped feat.params.

## Human-speech evaluation

Corpus. 88 real human recordings (58 distinct speaker ids: 40 LibriSpeech dev-clean
speakers, 29 African Accented French speakers; male and female; read and conversational
French), expanded to 440 clips with noise variants. Positives are 546 intended-
pronunciation TTS clips and 36 literal-spelling clips over 23 voices, 3 speeds
(100/135/175 wpm), 3 pitch/level conditions plus quiet, loud and simulated-distant
variants.

The TTS limitation is the main one and it is measured, not assumed. espeak-ng -q -x
shows that the literal brand spelling is not the wake word in either language:
fr oremi -> orm'i (/ɔʁmi/, the /e/ is elided), en oremi -> 'o@mi (/oʊəmi/, no /r/).
Positives therefore use the homophones the models actually expect: fr au rémi, ô Rémi,
eau rémi, haut rémi (= the configured au rr ei mm ii); en oh remi under espeak-ng, and
oremi under flite (the voice used by the committed fixture). The literal spelling is
kept as a separate label and, as predicted, fires 0/18 at 1e-15 in both languages.

Detection is also strongly voice-dependent, which is a property of TTS rather than of
human speech: for French only the espeak-ng fr+f1 and fr+f2 variants ever fire; fr,
fr+f3, fr+m1..fr+m3, fr-be and fr-ch never fire even at 1e-35. For English all five
flite voices (kal, kal16, awb, rms, slt) fire at 1e-25 and at 1e-15, while several
espeak-ng voices never do. Absolute true-positive rates below therefore describe TTS,
not people, and are reported as such.

Clean detection at the production threshold (1e-15): French intended positives 8/66
(12.1%), French literal 0/18, English intended 47/96 (49.0%), English literal 0/18.
At the permissive end (1e-30): French 20/66, English 55/96. Real human clean negatives:
French 0/38, English 3/50 (6.0%). Real human near-homophone negatives (English, 10
clips containing words like remi/remy): 0 detected at 1e-15, 1 at 1e-30.

## Noise evaluation

Synthetic: white and pink noise, generated deterministically. Real: ESC-50 recordings
grouped as fan/AC (vacuum cleaner, washing machine; ESC-50 has no air-conditioner
class), engine (engine, helicopter), keyboard/office (keyboard typing, mouse click),
street/traffic (car horn, siren, train), kitchen/home (pouring water, drinking,
can opening), crying child, weather (rain, wind, thunderstorm), clock/footsteps; plus
multi-talker babble built by summing four to six real human recordings. SNRs 20, 10 and
5 dB for the designed corpus, 10 dB for the real-human add-on. Mixing: RMS over the
whole clip, noise scaled to the target ratio, the sum scaled down (never clipped) if it
would exceed 0.99 FS; the measured post-mix SNR is recorded per file and peak scaling
preserves the ratio.

Result: noise did not degrade detection in this benchmark. The paired comparison at
1e-15 (same speech, clean vs its noisy variants) found zero bases that fired clean and
then stopped firing, and 7 French / 1 English bases that missed clean but fired under
noise. The French positive set fired under fan/AC (2-3 of 8 per SNR), pink (1-3), white
(0-2), babble (0-1) and weather (1-2) with no monotone SNR trend. Conclusion: this is a
property of the KWS margin, which grows with the frames since the last utterance reset
(the phone-loop penalty kws_plp accumulates every frame), not evidence that noise
improves the acoustics. It also means the reported false-positive rates under noise are
optimistic for longer continuous streams.

Real human speech plus real noise (false positives, count/n):

| Real human negatives | FR 1e-10 | FR 1e-15 | FR 1e-20 | EN 1e-10 | EN 1e-15 | EN 1e-20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| clean | 0/38 | 0/38 | 0/38 | 1/50 | 3/50 | 5/50 |
| + fan/AC | 0/38 | 0/38 | 0/38 | 0/50 | 0/50 | 1/50 |
| + keyboard/office | 0/38 | 0/38 | 0/38 | 0/50 | 2/50 | 2/50 |
| + street/traffic | 0/38 | 1/38 | 1/38 | 1/50 | 2/50 | 4/50 |
| + babble | 0/38 | 0/38 | 2/38 | 0/50 | 0/50 | 6/50 |

## Threshold sweep

Production semantics, all samples measured at every threshold. Positive = intended-
pronunciation wake word (clean and noisy); negative = everything that must not fire.

French (258 positives, 312 negatives):

| Threshold | TP | FN | FP | TPR | FPR | latency median / p90 (s) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1e-10 | 16 | 242 | 6 | 0.062 | 0.019 | 0.60 / 0.90 |
| 1e-12 | 23 | 235 | 10 | 0.089 | 0.032 | 0.60 / 0.75 |
| 1e-15 | 33 | 225 | 18 | 0.128 | 0.058 | 0.60 / 0.75 |
| 1e-17 | 37 | 221 | 20 | 0.143 | 0.064 | 0.60 / 0.75 |
| 1e-20 | 49 | 209 | 25 | 0.190 | 0.080 | 0.60 / 0.75 |
| 1e-25 | 68 | 190 | 37 | 0.264 | 0.119 | 0.55 / 0.70 |
| 1e-30 | 89 | 169 | 65 | 0.345 | 0.208 | 0.55 / 0.75 |

English (288 positives, 330 negatives):

| Threshold | TP | FN | FP | TPR | FPR | latency median / p90 (s) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1e-10 | 63 | 225 | 3 | 0.219 | 0.009 | 1.10 / 1.35 |
| 1e-12 | 69 | 219 | 4 | 0.240 | 0.012 | 1.10 / 1.35 |
| 1e-15 | 77 | 211 | 5 | 0.267 | 0.015 | 1.10 / 1.35 |
| 1e-17 | 82 | 206 | 5 | 0.285 | 0.015 | 1.10 / 1.35 |
| 1e-20 | 89 | 199 | 9 | 0.309 | 0.027 | 1.10 / 1.35 |
| 1e-25 | 112 | 176 | 11 | 0.389 | 0.033 | 1.05 / 1.35 |
| 1e-30 | 132 | 156 | 27 | 0.458 | 0.082 | 1.05 / 1.35 |

Trade-offs. Every step towards a smaller (more permissive) threshold buys true positives
and pays false positives; every step towards a larger (stricter) threshold does the
reverse, and the French model is already at 6.2% TPR at 1e-10. Note that detection is
not monotone in the threshold, because a detection restarts the utterance and truncates
the margin accumulation, so each row is an independent measurement and not a
re-derivation. Latency is measured from the start of the speech clip to the reported
detection; median latency is essentially flat across the sweep, which means a stricter
threshold does not buy earlier detections, only fewer.

Score distribution (strictest firing threshold on the ladder, log10): clean French
positives median -22 (39/66 never fire anywhere down to 1e-35, max -6); clean French
unrelated negatives median -30 (34/40 never fire); clean French similar-name negatives
median -16 with a max of -8, i.e. they overlap the positives; clean English positives
median -6 (37/96 never fire); clean English real-human negatives median -26 with a max
of -6. PocketSphinx exposes no hypothesis score for KWS (kws_search_hyp writes
out_score = 0); the only score is Segment.prob, which is logmath_exp(keyword HMM out
score minus best phone-loop out score minus KWS_MAX), i.e. already a phone-loop-relative
margin. This study converts it to an equivalent threshold.

## False-positive analysis

At 1e-15, French negatives that fired (18/312): 15 are the partial word oré (/oʁe/,
missing /mi/, TTS, all voices) and 3 are the real words auréole (2) and orénoque (1).
Clean unrelated French phrases: 0/40. Real human French: 0/38 clean.

At 1e-15, English negatives that fired (5/330): 2 partials (remi, oh re) and 3 real
human LibriSpeech utterances with no wake word. At 1e-10, 3/330 fire, one of them real
human. Real human English near-homophones (clips containing remi/remy): 0/10 at 1e-15.

Mechanism note. Almost every firing in both classes takes the form of a discriminant
detection immediately followed by the wake word, e.g. the hypothesis string remi oremi:
at 1e-15 English produces 68/77 positive firings and 5/5 negative firings as remi oremi.
is_discriminant_word only rejects an exact configured discriminant or a hypothesis whose
two halves are equal, so a hypothesis that contains both the discriminant and the wake
word is accepted. Rejecting any hypothesis that contains a discriminant would not be a
safe fix: it would also suppress 68/77 English and 16/33 French true positives, which
have exactly the same shape. This was measured before proposing anything.

## Latency and performance

| Metric | A 16 kHz (production) | B polyphase 8 kHz | B2 soxr 8 kHz |
| --- | ---: | ---: | ---: |
| FR TPR / FPR at 1e-15 | 0.128 / 0.058 | 0.112 / 0.058 | 0.116 / 0.058 |
| FR reset-free median log10 score | -35.44 | -37.13 | -37.27 |
| FR decoder init (ms) | 132.5 | 122.9 | n/a |
| FR decoder RSS (MB) | 21.9 | 6.2 | n/a |
| FR process_raw / 50 ms chunk (ms) | 1.448 | 1.429 | n/a |
| FR real-time factor | 0.0292 | 0.0285 | n/a |
| FR CPU per audio-hour (s) | 105.0 | 102.8 | n/a |
| FR utterance cycle (ms) | 0.030 | 0.026 | n/a |
| EN decoder at 8 kHz | works | FAILS | FAILS |
| EN TPR / FPR at 1e-15 | 0.267 / 0.015 | not applicable | not applicable |
| EN process_raw / 50 ms chunk (ms) | 1.568 | - | - |

Cost of a hypothetical in-process downsampler: the 129-tap polyphase FIR takes 0.378 ms
per audio-second (22.67 ms for 60 s), i.e. 1.36 s of CPU per audio-hour, about 1.3% on
top of the 105 s/audio-hour PocketSphinx decoding cost. It is affordable but buys
nothing measurable. Running ffmpeg/soxr per chunk costs 26.3 ms per audio-second and is
not a production option.

Latency: French detections are reported 0.55-0.60 s (median) and 0.70-0.90 s (p90) after
the start of the speech clip; English 1.05-1.10 s median and 1.35 s p90. Both include
the 10-frame kws_delay reporting window.

Harness fidelity: feeding the same PCM through the unmodified WakewordEngine at 1e-15
reproduced the study verdicts on 1,223 of 1,224 samples (99.92%). The single mismatch is
a marginal French positive detected at 8,000-byte chunks and missed at the study's
50 ms chunks, i.e. chunk-boundary sensitivity, not a logic difference.

## Decision

Sample rate - keep 16 kHz. Explicit 8 kHz processing is technically valid for the French
model (Configuration B builds and runs) but measured equal or worse: French TPR 0.128
vs 0.112 (B) and 0.116 (B2) at 1e-15 with identical false-positive rate, and a reset-free
median score 1.7 dex lower on clean speech and 0.5-0.9 dex lower under noise. The
theoretical reason is that the model band-limits itself to 3718.8 Hz, so the 16 kHz front
end already implements the 8 kHz analysis exactly; downsampling only adds a filter in
front of an identical filterbank. For English the question does not arise: 8 kHz is
rejected by PocketSphinx because upperf 6800 exceeds the 4 kHz Nyquist. Current 16 kHz
path: detection rate 12.1% clean / 12.8% overall (FR), 49.0% clean / 26.7% overall (EN);
false-positive rate 5.8% (FR), 1.5% (EN); latency 0.60 s / 1.10 s median. Explicit 8 kHz
path: detection rate 11.2% (FR, polyphase) and 11.6% (FR, soxr); false-positive rate
5.8%; latency unchanged; English not constructible.

Threshold - keep 1e-15. The evidence does not support a change in either direction.
Tightening to 1e-10 cuts French TPR from 12.8% to 6.2% and English from 26.7% to 21.9%
for a false-positive reduction of less than 4 points (FR 5.8% to 1.9%, EN 1.5% to 0.9%).
Loosening to 1e-20 gains French TPR 12.8% to 19.0% and English 26.7% to 30.9% but raises
false positives (FR 5.8% to 8.0%, EN 1.5% to 2.7%), and the false positives that matter
most - real human speech - already occur at 1e-10 and even at 1e-6 for some English
utterances, so loosening is the wrong direction for reliability. The 1e-15 constant is
also not what limits French recall: 39/66 clean French positives never fire at any
threshold down to 1e-35, which is a model/TTS-pronunciation limit, not a threshold one.

No change to is_discriminant_word is justified either: the remi oremi hypothesis shape is
shared by 68/77 English true positives and 5/5 English false positives at 1e-15.

## Changes made

Production code: none. No file under ohunerin/ was modified.

Repository changes:
- .gitignore: added .tmp/ so the scratch corpus used by this study cannot be committed
  accidentally. The repository already documents .tmp/ for scratch data (AGENTS.md uses
  .tmp/uvcache).
- benchmarks/wakeword_study/: the reproducible harness (corpus builder, PocketSphinx
  probe, study runner, analyser, front-end equivalence check, production verification,
  performance benchmark, README). No audio is committed; the corpus is downloaded or
  synthesized into .tmp/ at run time.

## Tests

Final test count: 75 passed (unchanged baseline: .venv/bin/python -m pytest tests/ -q).
No test was added because no production behaviour changed; the existing suite already
covers the streaming, decoder-drift, pool and fixture guarantees that the study was
required not to regress, and it still passes. ruff check . --no-fix reports only the
pre-existing tests/test_models.py:22 F401 baseline finding; bandit -c bandit.yaml -r
ohunerin -q is clean.

Relevant benchmark results:
- Harness fidelity: 1,224 samples checked against the unmodified WakewordEngine at
  1e-15, 1 mismatch (chunk-size sensitivity).
- Front-end equivalence: French filterbank identical at 16 kHz/512 and 8 kHz/256
  (236 coefficients, highest bin 3718.8 Hz); English rejected at 8 kHz.
- Corpus: 1,576 samples (582 positives, 994 negatives), 58 human speaker ids, 23 TTS
  voices, 12 acoustic noise conditions, SNRs 20/10/5 dB and 10 dB.
- Sweep: French 16/23/33/37/49/68/89 true positives at 1e-10/1e-12/1e-15/1e-17/1e-20/
  1e-25/1e-30; English 63/69/77/82/89/112/132.
- Sample rate: French A/B/B2 TPR 0.128/0.112/0.116 at 1e-15; margins -35.44/-37.13/
  -37.27; mismatch controls -45.27/-50.52; English 8 kHz not constructible.
- Performance: process_raw 1.448 ms per 50 ms chunk (FR, RTF 0.0292); downsampling
  0.378 ms per audio-second.

## Remaining uncertainty

- No human recording of the wake word exists. Positives are TTS and the study shows this
  is not representative: detection depends strongly on the synthetic voice (French fires
  only on fr+f1/fr+f2; several voices never fire at any threshold). Absolute true-positive
  rates here are TTS figures and must not be read as expected human performance. The
  relative comparisons (16 kHz vs 8 kHz, threshold ordering, false-positive structure)
  are the results that transfer.
- No real-room far-field recordings were available and no microphone exists in this
  environment, so the distance condition is a synthetic RIR convolution and is labelled
  as such. Far-field and reverberant real-world behaviour remains unmeasured.
- Corpus size: 66 clean French and 96 clean English TTS positives over 23 voices;
  differences smaller than a few points are not statistically meaningful. The French
  near-miss false-positive rate rests on 16 near-homophone and 6 partial clips.
- The study used 50 ms chunks; the reference client sends 250 ms. One sample in 1,224
  changed verdict with chunk size, so chunk-boundary sensitivity is real but small and
  was not characterised across the full corpus.
- The finding that noise added detections is reproducible in this corpus but its exact
  cause was not isolated. The margin-accumulation explanation is inferred from
  kws_search.c (the phone-loop penalty kws_plp is applied every frame between resets);
  it was not confirmed by instrumenting the native search.
- Why the wake word fires at all on unrelated speech, noise and real human audio was not
  established at the acoustic level. The measured structure (discriminant plus wake word
  in the same 10-frame window) is documented, but the underlying model behaviour needs
  deeper instrumentation.
- All measurements come from one machine, one PocketSphinx build (5.1.1) and one
  process configuration; cross-build stability was not tested.
- The committed regression fixtures were generated with espeak-ng/flite and were not
  independently validated against human speech in this study.