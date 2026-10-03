# French wake-word pronunciation and model investigation

Follow-up to REPORT.md (sample rate and threshold). No production code was modified.
Harness: benchmarks/wakeword_study (pronunciation.py, model_probe.py, human_probe.py,
streaming.py, pronunciation_analysis.py).

## 1. Root cause

The French wake word is limited by three independent things, in this order:

1. **Acoustic margin, not the threshold.** For every plausible pronunciation the
   keyword margin of a correctly pronounced "oremi" sits far below the production
   threshold. On the controlled corpus, the median equivalent threshold of the studied
   pronunciations is between 1e-31 and 1e-39, i.e. 16 to 24 orders of magnitude below
   kws_threshold=1e-15; only the extreme tail clears it. Even with a keyphrase whose
   phones match the spoken pronunciation exactly (au rr ei mm ii vs an /o ʁe mi/ clip),
   0/18 clips fire at 1e-15, 7/18 only fire if the threshold is loosened to 1e-30 or
   below, and 11/18 never fire at all down to 1e-200. Pronunciation correction alone
   therefore cannot rescue French recall.
2. **The engine searches one pronunciation, and not the best one.** config.json declares
   three French pronunciations and four English ones, but _configure_keyphrases() writes
   only entry.word into the keyphrase file, and kws_search_reinit() resolves a keyphrase
   with dict_wordid() + dict_pron(), which returns the primary pronunciation only. The
   oremi(2) / oremi(3) entries that _add_dictionary_entry() adds are in the dictionary
   and invisible to the search. The pronunciation that is actually searched
   (oo rr ei mm ii = /ɔ ʁe mi/) has the lowest rank quality of the plausible variants
   (AUC 0.631 against 0.693 for /o ʁe mi/ and 0.709 for /ɔ ʁɛ mi/).
3. **TTS is not a valid proxy for human speech, and the corpus voice bias is extreme.**
   On the same French model, real human French words often score higher than espeak-ng
   renderings of the same word (chose: 1e+3.6 vs 1e+0.2 median margin; année: 1e+2.0 vs
   1e-15.6), and 84% of human utterances that contain the keyphrase word fire at 1e-15.
   Within the TTS corpus, only espeak-ng fr+f1 and fr+f2 ever produce detections for the
   wake word; fr, fr+f3, fr+m1..fr+m3, fr-be and fr-ch never fire at any threshold.

The discriminant is not part of the problem: removing the remi keyphrase changes the
keyword margin of exactly 0 of 1720 French samples and 0 of 836 English samples.

Sample rate and threshold were already excluded by the first study and were not revisited.

## 2. Evidence

| Experiment | What it measured | Result |
| --- | --- | --- |
| Config trace | what PocketSphinx actually searches | get_kws() = remi, dikomlam, oremi; lookup_word(oremi) = oo rr ei mm ii; oremi(2)/(3) present in the dictionary but absent from the keyphrases |
| Dictionary convention probe | meaning of the phone tokens | oo = /ɔ/ (pomme, or, omelette), au = /o/ (mot, beau), ou = /u/, ei = /e/ (rémi), ai = /ɛ/ (très), ee = /ə/ (petit) |
| Controlled pronunciation benchmark | 8 pronunciations x 9 voices x 2 speeds = 144 clips, plus the 1576-sample study corpus, 8 keyphrase/dictionary variants, threshold 1e-15 and reset-free margins | see section 3 |
| English pronunciation variants | same, for the 4 configured English pronunciations | en_current J +0.235, en_multi J +0.229 (FPR 1.7% -> 4.9%) |
| Discriminant control | margins with and without the remi keyphrase | 0 differing samples in FR (1720) and EN (836) |
| Model vocabulary probe | 40 in-dictionary French words x 8 voices, each as its own keyphrase | model fires well on many words (mot, or, très, oreille, père 8/8) and never on others (note, omelette, café, bébé, musée, rémi 0/8) |
| Real-human word probe | 21 in-dictionary words, real AFF speech containing the word vs not | 84% of containing utterances fire at 1e-15, but 45% of non-containing utterances fire too |
| Streaming benchmark | 8 chunk sizes x 5 kws_delay values, 500 FR + 452 EN samples, byte-for-byte WakewordEngine mirror | see section 6 |
| Fixture check | committed FR/EN fixtures under every candidate variant and 7 chunk sizes | detected in 7/7 chunk sizes for every candidate |

## 3. Pronunciation analysis

Configured representation (config.json -> Decoder):

| Layer | Value |
| --- | --- |
| Wake-word string | oremi |
| Dictionary entries added | oremi = oo rr ei mm ii (/ɔ ʁe mi/), oremi(2) = oo rr ai mm ii (/ɔ ʁɛ mi/), oremi(3) = au rr ei mm ii (/o ʁe mi/) |
| Keyphrase file written by the engine | oremi, remi, dikomlam |
| Pronunciation KWS actually uses | oo rr ei mm ii = /ɔ ʁe mi/ (the rest are dead configuration) |
| Discriminant | remi = rr ei mm ii, searched but inert |

Candidate alternatives, same corpus, threshold 1e-15 (312 intended positives: 276 TTS
study positives + 36 controlled /o ʁe mi/ and /ɔ ʁe mi/ clips; 464 French negatives):

| Keyphrase phones | IPA | TP | TPR | FP | FPR | Youden J | real-human FP | AUC |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| oo rr ei mm ii (current) | ɔ ʁe mi | 39/312 | 0.125 | 19/464 | 0.041 | +0.084 | 1/190 | 0.631 |
| au rr ei mm ii | o ʁe mi | 33/312 | 0.106 | 14/464 | 0.030 | +0.076 | 2/190 | 0.693 |
| oo rr ai mm ii | ɔ ʁɛ mi | 47/312 | 0.151 | 24/464 | 0.052 | +0.099 | 1/190 | 0.709 |
| au rr ee mm ii | o ʁə mi | 4/312 | 0.013 | 6/464 | 0.013 | 0.000 | 3/190 | 0.455 |
| au rr mm ii | o ʁm i | 6/312 | 0.019 | 22/464 | 0.047 | -0.028 | 18/190 | 0.438 |
| all three configured, as 3 keyphrases | - | 62/312 | 0.199 | 31/464 | 0.067 | +0.132 | 3/190 | 0.697 |
| two /e/ variants as 2 keyphrases | - | 48/312 | 0.154 | 25/464 | 0.054 | +0.100 | 3/190 | 0.678 |
| current, remi keyphrase removed | - | 39/312 | 0.125 | 19/464 | 0.041 | +0.084 | 1/190 | 0.631 |

At matched false-positive rates the ordering is stable: at FPR 0.10 the TPRs are
current 0.221, /o ʁe mi/ 0.210, /ɔ ʁɛ mi/ 0.288, all-three 0.257; at FPR 0.02 the
all-three variant is worse than the current one (0.045 vs 0.071), because taking the
maximum over three searches lifts the negative tail too.

Two families are rejected outright on measurement: elided (/o ʁmi/, /ɔ ʁmi/) and schwa
(/o ʁə mi/) keyphrases score AUC below 0.5 - they fire on ordinary French more than on
the wake word, because rr ee mm ii (/ʁəmi/) is the most common sequence in the language
(remis, remise, premier).

Failure classification for the 36 controlled /o ʁe mi/ + /ɔ ʁe mi/ clips (A = phones
differ from the keyphrase, B = phones match but margin stays below 1e-30, D = fires only
when the threshold is loosened past 1e-15):

| Keyphrase | Spoken | detected at 1e-15 | D (threshold-limited) | B (acoustic failure) | A (wrong pronunciation) |
| --- | --- | ---: | ---: | ---: | ---: |
| ɔ ʁe mi (current) | o ʁe mi | 2/18 | 3 | 0 | 13 |
| ɔ ʁe mi (current) | ɔ ʁe mi | 3/18 | 8 | 7 | 0 |
| o ʁe mi | o ʁe mi | 0/18 | 7 | 11 | 0 |
| ɔ ʁɛ mi | o ʁe mi | 3/18 | 8 | 0 | 7 |

The last two rows are the important ones: when the keyphrase is exactly right, most
clips still fail acoustically (B), or only clear the bar when the threshold is loosened
(D). Category A explains most of the current variant failures but correcting it moves
the problem rather than removing it.

## 4. Human speech results

No human recording of the wake word exists in the repository or in any public corpus that
could be located: LibriSpeech dev-clean and African Accented French contain no occurrence
of the invented name, and the only Tatoeba French sentence containing "Rémi" has no audio.
The absolute French true-positive rate therefore remains a TTS figure. A collection
protocol is committed as HUMAN_RECORDING_PROTOCOL.md (speakers, prompts, conditions,
capture format, metadata, licensing, analysis procedure, success criterion).

What could be measured with real human speech is the model behaviour on in-vocabulary
words. Making a word that occurs in the African Accented French transcript its own
keyphrase and running it over human utterances (21 words, 192 containing clips, 40
non-containing clips):

* utterances that **do** contain the keyphrase word: mean 84% fire at 1e-15 (median 92%);
* utterances that **do not**: mean 45% fire at 1e-15 (median 42%).

So the French model is not deaf to human speech - it detects it readily - but one-word KWS
keyphrases are over-permissive for short common words (temps 40/40, vie 40/40, homme
39/40, main 39/40 non-containing utterances fire; bonjour, problème and marché 0/40).
The wake word is longer and out of vocabulary, and its measured false-positive rate on
real human French is low (1/190 real human or real-human+noise clips at 1e-15).

TTS-vs-human for the same word (median equivalent threshold, TTS probe vs human probe):

| Word | TTS | Human |
| --- | ---: | ---: |
| chose | 1e+0.2 | 1e+3.6 |
| année | 1e-15.6 | 1e+2.0 |
| mort | 1e-11.8 | 1e+2.0 |
| idée | 1e-12.8 | 1e+0.2 |
| problème | 1e-38.9 | 1e-12.5 |
| été | 1e-2.0 | 1e-10.3 |
| mère | 1e+17.4 | 1e-1.0 |
| frère | 1e+6.4 | 1e-14.9 |

Human is higher for four of the eight and much higher for the first four; no factor is
consistent across all words, so TTS error is not a simple constant offset. The conclusion
that holds is the weak one: absolute TTS recall must not be reported as human recall.

## 5. Model analysis

The model is a legitimate French 8 kHz PTM model (cmusphinx-fr-ptm-8khz-5.2) with a
complete phone inventory for every token used by the wake word (oo, rr, ei, ai, au, ee,
ii, mm are all in the mdef and all appear in the 105k-entry dictionary). It is not
mismatched to the language, the dictionary conventions are internally consistent, and
it recognises its own vocabulary in both TTS and human speech. It should not be replaced.

What the vocabulary probe adds is that per-word reliability varies enormously and is not
predictable from the phone inventory alone. At 1e-15, across eight espeak-ng voices of
the same word:

| Fires 8/8 | 6-7/8 | 3-5/8 | 0-2/8 |
| --- | --- | --- | --- |
| mot, or, très, oreille, père | vélo, moto, opéra, orange, marché, frère, mère, affaire, été | chose, rose, mort, orage, idée, année, même, réveil, pareil, aimer | pomme, note, omelette, menu, rémi, café, bébé, musée, préféré, premier, chevalier, soleil, problème, système, auréole, beau |

Aggregating by phone content, words whose pronunciation contains the ei phone (/e/) fire
in 24% of voice-clips on average (12 words) against 52% for words without it (28 words).
The wake word uses ei in the pronunciation the engine actually searches. This is
consistent with the ranking result that the ai (/ɛ/) keyphrase ranks better than the ei
keyphrase for the same audio (AUC 0.709 vs 0.693) and with rémi itself firing 1/8 in TTS.
This is a model-specific vowel confusion, not a dictionary error: the dictionary
transcribes rémi as rr ei mm ii exactly as convention requires.

## 6. Streaming analysis

Chunk size (FR: 228 positives, 272 negatives; EN: 114 positives, 338 negatives; identical
PCM, kws_delay=10, verdicts compared with the 250 ms reference):

| Chunk | FR positives | FR negatives | FR agreement | EN positives | EN negatives | EN agreement |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 ms | 23/228 | 5/272 | 0.998 | 47/114 | 9/338 | 1.000 |
| 20 ms | 23/228 | 5/272 | 0.998 | 47/114 | 9/338 | 1.000 |
| 25 ms | 23/228 | 5/272 | 0.998 | 47/114 | 9/338 | 1.000 |
| 50 ms | 23/228 | 5/272 | 0.998 | 47/114 | 9/338 | 1.000 |
| 100 ms | 23/228 | 5/272 | 0.998 | 47/114 | 9/338 | 1.000 |
| 125 ms | 24/228 | 5/272 | 1.000 | 47/114 | 9/338 | 1.000 |
| 250 ms | 24/228 | 5/272 | 1.000 | 47/114 | 9/338 | 1.000 |
| 500 ms | 24/228 | 5/272 | 1.000 | 47/114 | 9/338 | 1.000 |

The previous study single mismatch is reproduced exactly and is systematic, not random:
tts-fr-pos-064 is detected for every chunk >= 125 ms and missed for every chunk <= 100 ms.
No other sample changes verdict at any chunk size. English is chunk-size invariant from
10 ms to 500 ms. The streaming semantics do not need fixing; the client block size
(250 ms) is inside the safe region.

kws_delay (250 ms chunks):

| kws_delay | FR positives | FR negatives | FR latency median/p90 | EN positives | EN negatives | EN latency median/p90 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 23/228 | 5/272 | 0.31 / 0.40 | 42/114 | 6/338 | 0.69 / 1.17 |
| 5 | 23/228 | 5/272 | 0.31 / 0.40 | 47/114 | 7/338 | 0.93 / 1.23 |
| 10 | 24/228 | 5/272 | 0.32 / 0.41 | 47/114 | 9/338 | 0.94 / 1.23 |
| 20 | 24/228 | 5/272 | 0.32 / 0.42 | 47/114 | 9/338 | 0.94 / 1.26 |
| 40 | 24/228 | 5/272 | 0.32 / 0.42 | 47/114 | 9/338 | 0.94 / 1.26 |

kws_delay changes detection, not only reporting: at 0 the English true-positive count
drops from 47 to 42 (and false positives from 9 to 6); at 5 it is 47 but with 7 false
positives. latency scales with the delay. kws_delay=10 is a reasonable operating point;
reducing it to cut latency costs recall, so it should not be changed.

## 7. Discriminant analysis

The remi keyphrase is inert. Removing it from the search changes the keyword margin of
0 of 1720 French samples and 0 of 836 English samples, and the production-semantics
verdicts are identical (FR 39/312 true positives, 19/464 false positives at 1e-15 in both
configurations).

The "remi oremi" hypothesis shape is a consequence of how kws_search_hyp() concatenates
every detection inside the kws_delay window, not of any suppression that is failing: the
decoder reports both keyphrases, and is_discriminant_word() only rejects an exact
configured discriminant or a string whose two space-separated halves are equal. Rejecting
every hypothesis that contains a discriminant token is unsafe - the same shape accounts
for 68/77 English and 16/33 French true positives at 1e-15 in the earlier study - and
would not help, because the discriminant contributes nothing to the margin in the first
place. No change to is_discriminant_word() is justified.

One existing quirk is worth recording rather than changing: is_discriminant_word() treats
"oremi oremi" as a structural discriminant (equal halves), so a user who repeats the wake
word twice in a row is suppressed. This predates the study and is outside its scope.

## 8. Candidate fixes

| Candidate | Change | FR TPR | FR FPR | FR J | FR real-human FP | EN TPR | EN FPR | EN J | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline | none | 0.125 | 0.041 | +0.084 | 1/190 | 0.252 | 0.017 | +0.235 | - |
| search all configured pronunciations | engine writes oremi(2)..(N) as keyphrases, normalises the returned word | 0.199 | 0.067 | +0.132 | 3/190 | 0.278 | 0.049 | +0.229 | mixed: clear FR gain, EN regression |
| search the two /e/ variants | same, only oremi and oremi(2) where (2) is au rr ei mm ii | 0.154 | 0.054 | +0.100 | 3/190 | - | - | - | smaller FR gain, same FP cost |
| replace the FR primary with oo rr ai mm ii | config.json only | 0.151 | 0.052 | +0.099 | 1/190 | unchanged | unchanged | unchanged | FR-only gain, model-specific vowel hack |
| elided / schwa pronunciations | config.json | 0.013-0.019 | 0.013-0.047 | <=0 | 3-18/190 | - | - | - | rejected, AUC < 0.5 |
| reduce kws_delay | config.json / engine | 0.101 | 0.018 | - | - | 0.219 | 0.013 | - | rejected, costs recall and latency gain is small |
| reject hypotheses containing a discriminant | is_discriminant_word() | suppresses 16/33 FR and 68/77 EN true positives | - | - | - | - | - | - | rejected in the first study, re-confirmed |

Latency is essentially unchanged by every candidate (FR 0.31-0.32 s, EN 0.94 s median,
measured with the same streaming harness), and every candidate keeps the committed FR and
EN fixtures detected for all seven regression chunk sizes (320 B to 64 kB).

The minimal implementation of the first candidate, for the record, is inside
_configure_keyphrases(): iterate over every entry.phones index and write
"{word}" / "{word}(N)" lines instead of the bare entry.word, and normalise any returned
hypothesis token word(N) back to word before it leaves process_raw(). It is not applied.

## 9. Production change

**None.** No file under ohunerin/ was modified.

Why the demonstrated defect is not fixed: it is real - the engine ignores two of three
French and three of four English configured pronunciations - but making the configuration
effective is a mixed result, not an improvement. It raises French Youden J from +0.084 to
+0.132 and French TPR from 0.125 to 0.199, but it also triples the English false-positive
rate (1.7% to 4.9%) and lowers English J from +0.235 to +0.229. WakewordEngine is
language-agnostic, so the change cannot be applied to French only without an unjustified
special case. The French-only alternative (replace the primary pronunciation with
oo rr ai mm ii) is justified by a model-specific vowel confusion measured only on TTS, and
the failure classification shows it would not address the root cause: even with an exact
phone match, 11 of 18 controlled clips never fire at all.

What would change the decision: human wake-word recordings. The human word probe shows the
model detects real human French much more readily than espeak-ng audio of the same word,
so the TTS-derived French figures are likely pessimistic and may reverse the FR-vs-EN
trade-off. The protocol and the gating criterion (human TPR gain at equal human FPR, larger
than the binomial confidence interval, with no English regression and no fixture
regression) are committed in HUMAN_RECORDING_PROTOCOL.md.

## 10. Validation

| Check | Result |
| --- | --- |
| .venv/bin/python -m pytest tests/ -q | 75 passed (unchanged baseline) |
| ruff check . --no-fix | only the pre-existing tests/test_models.py:22 F401 |
| ruff check --no-fix benchmarks/ | clean |
| bandit -c bandit.yaml -r ohunerin -q | clean |
| Committed fixtures under every candidate variant, chunk sizes 320 B - 64 kB | detected in 7/7 for all candidates |
| Harness fidelity (previous study, still valid) | 1223/1224 verdicts reproduced by the real WakewordEngine |
| Production code diff | none |

Measured candidate results are in section 8; the raw files are
.tmp/wakeword_study/pronunciation_results.json, pronunciation_margins_fr.json,
pronunciation_margins_en.json, model_probe_results.json, human_probe_results.json and
streaming_results.json, all reproducible from benchmarks/wakeword_study/README.md.

## 11. Remaining limitations

* **No human wake-word recordings.** Every positive in this study is synthetic. The human
  word probe shows the model behaves differently on human speech, so the absolute French
  recall numbers (12.5% at 1e-15) cannot be read as human performance, and the candidate
  ranking could change once human data exists.
* The controlled pronunciation corpus is espeak-ng phoneme synthesis: it removes the
  spelling-to-phoneme ambiguity but is not human articulation, and espeak-ng renders /o/
  and /ɔ/ with its own voice characteristics.
* The French negative set is deliberately adversarial (204 near-homophones, 62 partial
  words, 136 similar names). The false-positive rates here are not deployment rates.
* The English side of the pronunciation comparison uses only the study TTS corpus; no
  English counterpart of the controlled pronunciation corpus was built.
* The model vocabulary probe covers 40 words over 8 voices; per-word variability is large
  and the ei-vs-ai aggregate is confounded by word identity.
* The real-human word probe uses one corpus (African Accented French) and one word per
  keyphrase; its 45% unrelated-speech firing rate is a property of one-word keyphrases in
  that corpus, not a calibrated false-alarm rate.
* The kws_delay effect on detection was measured, not explained at the source level
  (kws_detections_hyp_str() and the reset on every hypothesis interact); the recommendation
  to keep 10 is empirical.
* Chunk-size sensitivity was probed on 500 French and 452 English samples; a single
  marginal sample changes verdict below 125 ms, so an exhaustive characterisation across
  the full corpus was not done.
* All measurements come from one machine, one PocketSphinx build (5.1.1) and one model
  snapshot.