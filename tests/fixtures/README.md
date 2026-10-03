# Wake-word regression fixtures

These files are fixed 16 kHz mono signed 16-bit little-endian PCM recordings used
by `tests/test_wakeword_streaming.py` so wake-word detection can be asserted
deterministically and offline. They are intentionally committed: regenerating them
requires a TTS engine that is not part of the test environment.

| File                            | Word    | Language | Duration |
| ------------------------------- | ------- | -------- | -------- |
| `wakeword-en-oremi-16k.raw`     | "oremi" | `en`     | 0.82 s   |
| `wakeword-fr-oremi-16k.raw`     | "oremi" | `fr`     | 1.32 s   |

## Provenance

English fixture, synthesized with CMU flite (BSD-style license):

```sh
flite -t "oremi" -o oremi.wav
ffmpeg -y -i oremi.wav -ac 1 -ar 16000 -f s16le wakeword-en-oremi-16k.raw
```

French fixture, synthesized with espeak-ng (the plain "oremi" spelling is not
pronounced with the phones the French model expects, so the near-homophone
"au rémi" is used; the decoder reports the configured `oremi` keyphrase):

```sh
espeak-ng -v fr+f2 -s 110 -w oremi.wav "au rémi"
ffmpeg -y -i oremi.wav -ac 1 -ar 16000 -f s16le wakeword-fr-oremi-16k.raw
```

Both recordings are validated by the test suite; a change to the acoustic models,
the dictionary or the keyword threshold must be re-validated against them.
