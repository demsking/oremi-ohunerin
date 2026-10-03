# Wake-word reliability study

Reproducible harness for the investigation into the French acoustic model's sample
rate and the `kws_threshold=1e-15` constant. It is self-contained and never touches
production code; it writes everything to `.tmp/wakeword_study` (gitignored).

## What it does

| Module | Purpose |
| --- | --- |
| `corpus.py` | Builds the evaluation corpus: pronunciation-validated TTS positives and negatives, real human negatives (LibriSpeech dev-clean, African Accented French), real environmental noise (ESC-50), synthetic noise, and SNR-controlled noisy variants. |
| `psprobe.py` | PocketSphinx probe. Recovers the keyword margin from `Segment.prob` (the Python hypothesis score is always 0 by construction) and reproduces `WakewordEngine.process_raw` exactly, including the utterance reset on every hypothesis. |
| `run_study.py` | Runs the production-semantics threshold ladder and the reset-free margin passes. |
| `analyze.py` | Renders the report tables. |
| `fecheck.py` | Ports `fe_build_melfilters()` to numpy and shows the 16 kHz and 8 kHz front ends build an identical filterbank for the French model. |
| `verify_production.py` | Feeds the same PCM through the real `WakewordEngine` and compares verdicts sample by sample. |
| `run_perf.py` | Decoder init, `process_raw`, utterance lifecycle, resampling CPU and RSS. |
| `pronunciation.py` | Controlled pronunciation benchmark. Synthesizes exact pronunciations with espeak-ng phoneme input, defines keyphrase/dictionary variants for both languages, and runs production-semantics passes and reset-free margin passes. |
| `pronunciation_analysis.py` | Tables for the pronunciation benchmark (overall, by spoken pronunciation, by voice, by negative set). |
| `model_probe.py` | Acoustic-model sanity probe: makes each in-dictionary French word its own keyphrase and measures whether the model fires on its own vocabulary across eight voices. |
| `human_probe.py` | Real-human equivalent: makes a word that occurs in the African Accented French transcripts its own keyphrase and measures detection on the human utterance that contains it versus human utterances that do not. |
| `streaming.py` | Chunk-size (10-500 ms) and `kws_delay` (0-40) behaviour with a byte-for-byte `WakewordEngine` mirror. |
| `HUMAN_RECORDING_PROTOCOL.md` | Collection protocol for real human wake-word recordings, the missing piece. |

## Reproduce

```sh
# 1. Fetch the three public corpora (LibriSpeech CC BY 4.0, ESC-50 CC BY-NC 3.0,
#    African Accented French CC BY-SA 4.0) and build the corpus (~3.4 GB, .tmp only).
.venv/bin/python -m benchmarks.wakeword_study.corpus

# 1b. Add the real-human-speech + real-noise negatives and evaluate them.
.venv/bin/python -m benchmarks.wakeword_study.add_real_noisy

# 2. Run the measurement passes (~11 min on 12 workers).
.venv/bin/python -m benchmarks.wakeword_study.run_study --workers 12

# 3. Render the tables.
.venv/bin/python -m benchmarks.wakeword_study.analyze --section all

# 4. Harness fidelity and front-end equivalence.
.venv/bin/python -m benchmarks.wakeword_study.verify_production
.venv/bin/python -m benchmarks.wakeword_study.fecheck
.venv/bin/python -m benchmarks.wakeword_study.run_perf

# 5. Pronunciation investigation (second study).
.venv/bin/python -m benchmarks.wakeword_study.pronunciation --stage build
.venv/bin/python -m benchmarks.wakeword_study.pronunciation --stage screen --thresholds 1e-15
.venv/bin/python -m benchmarks.wakeword_study.pronunciation --stage margins \
  --out .tmp/wakeword_study/pronunciation_margins_fr.json
.venv/bin/python -m benchmarks.wakeword_study.pronunciation --stage margins --workers 3 \
  --variants en_current,en_multi,en_multi2 --out .tmp/wakeword_study/pronunciation_margins_en.json
.venv/bin/python -m benchmarks.wakeword_study.pronunciation_analysis --section all

# 6. Model and human probes, streaming behaviour.
.venv/bin/python -m benchmarks.wakeword_study.model_probe --stage run
.venv/bin/python -m benchmarks.wakeword_study.human_probe --stage run
.venv/bin/python -m benchmarks.wakeword_study.streaming
```

## Key measurement notes

* `Decoder.hyp().score` is useless: `kws_search_hyp()` writes `out_score = 0`. The only
  keyword score PocketSphinx exposes is `Segment.prob`, which is
  `logmath_exp(keyword_margin - KWS_MAX)`. `psprobe.prob_to_threshold()` inverts it into
  the equivalent `kws_threshold`.
* Detection is **not monotone** in `kws_threshold`, because a detection restarts the
  utterance and the KWS margin accumulates phone-loop penalties over the frames since the
  last restart. Every threshold is therefore measured with its own production pass.
* The corpus never commits audio: it is downloaded or synthesized into `.tmp/`, which is
  gitignored.