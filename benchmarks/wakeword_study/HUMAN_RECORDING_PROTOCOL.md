# Human wake-word recording protocol

## Why this is needed

Every wake-word *positive* in the reliability study is synthetic. The study measured
that this is not a neutral substitution: in the same French acoustic model, the
controlled pronunciation benchmark and the real-human probe give different pictures,
and the model fires on real human French with much higher margins than on espeak-ng
audio of the same word in several cases (chose: human median margin 1e+3.6 vs TTS
1e+0.2; année: 1e+2.0 vs 1e-15.6). Absolute French true-positive rates derived from TTS
must therefore not be treated as human wake-word performance, and no dictionary or
threshold decision should be based on them alone.

No human recording of the wake word exists in this repository or in any public corpus
that could be located (LibriSpeech and African Accented French contain no occurrence of
the invented name; the single Tatoeba French sentence containing "Rémi" has no audio).
This document is the collection protocol to close that gap.

## Speakers

* At least 10 speakers, French native or fluent, with a written consent form.
* Both sexes represented, and at least three accent groups (metropolitan France,
  Belgium/Switzerland, Canada, North/West Africa) if available.
* At least 5 repetitions of the wake word per speaker, spread across conditions.
* Target: 300+ analysed positives so a 10-point TPR difference is meaningful.

## Prompts

Each speaker records, in random order:

| Category | Examples | Purpose |
| --- | --- | --- |
| Intended wake word | "oremi", "Oremi", "hé oremi", "ok oremi" | the target |
| Alternate readings | "au rémi", "ô Rémi", "eau rémi", "au remi" | the two phone families in config.json |
| Near misses | "rémi", "rémi et moi", "orémie", "orémus", "rémige" | false-positive guard |
| Similar names | "Aurélie", "Amélie", "Jérémie", "Roméo" | false-positive guard |
| Unrelated sentences | 10 neutral French sentences | false-positive guard |

## Conditions (per speaker, per prompt family)

* normal speech, quiet speech, loud speech;
* close talk (10-20 cm), desk distance (50 cm), room distance (2-3 m);
* quiet room, room with fan/AC, room with television or background conversation.

Record a 1 s of room tone before and after every clip so the SNR can be measured.

## Capture specification

* 16 kHz, mono, signed 16-bit little-endian PCM, exactly what the WebSocket protocol
  expects; no AGC, no noise suppression, no gain normalisation, no resampling.
* One file per prompt; keep the raw device output alongside the converted PCM.
* Record the device model, the host OS capture path, and whether any OS-level
  processing (AGC, beamforming, echo cancellation) was active.

## Metadata per clip

Same fields as `corpus.py` samples, plus: `speaker_id`, `sex`, `accent_group`,
`distance_cm`, `environment`, `device`, `consent_ref`, and a `pronunciation_audited`
field holding the phone sequence two independent annotators agree the speaker produced
(in the model phone conventions: `oo rr ei mm ii`, `au rr ee mm ii`, ...). Clips whose
audited pronunciation is disputed are excluded from the primary analysis and reported
separately.

## Licensing and storage

* Written consent covering research use; state whether redistribution is allowed.
* Prefer an explicit licence (CC BY 4.0 or CC BY-SA 4.0) when the speaker agrees,
  otherwise store internally and mark the manifest `license: internal-only`.
* Never commit the audio. Store it under `.tmp/wakeword_study/human/` (gitignored) and
  commit only the manifest template and this protocol.

## Analysis procedure

1. Build a manifest with the fields above, `kind: positive` for wake-word clips and
   `kind: negative` for the guards, and register it as a sample list for
   `benchmarks/wakeword_study/pronunciation.py`.
2. Run the margin pass and the production pass for every candidate variant at 1e-10,
   -12, -15, -17, -20, -25, -30.
3. Report human TPR/FPR **separately** from TTS; never pool them.
4. Compare the current pronunciation, the configured alternates, and any candidate
   against the human set before changing `config.json` or `ohunerin/engines/wakeword.py`.
5. Success criterion: the candidate must improve human TPR at equal human FPR by more
   than the binomial confidence interval of the sample, and must not regress the
   committed fixtures or the English language.