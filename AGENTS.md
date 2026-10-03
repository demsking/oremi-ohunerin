# AGENTS.md

Instructions for AI coding agents working in this repository.

Scope: this file. It is written to be read before your first edit. It documents
what the code actually does (verified against the working tree), not what the
marketing docs claim. Where the two disagree, this file says so explicitly —
see [Known traps and stale artifacts](#13-known-traps-and-stale-artifacts).

---

## 1. Project at a glance

|                |                                                                                 |
| -------------- | ------------------------------------------------------------------------------- |
| Name           | `oremi-ohunerin`                                                                |
| Version        | `4.0.0b10` (see `pyproject.toml`)                                               |
| Purpose        | Real-time ambient sound detection + wake word detection server                  |
| Role           | Audio-detection component of the _Oremi Personal Assistant_                     |
| Language       | Python **3.11 only** (`requires-python = ">=3.11,<3.12"`)                       |
| License        | Apache-2.0, © Sébastien Demanou                                                 |
| Canonical repo | GitLab — `gitlab.com/demsking/oremi-ohunerin` (branch: `main`)                  |
| Docs           | `README.md`, `DOCUMENTATION.md`, `CONTRIBUTING.md`, and the served `/docs` page |
| Code size      | ~2,260 lines in `ohunerin/`, ~1,148 lines in `tests/`                           |

Ohunerin is a **WebSocket server**. Clients stream raw PCM audio; the server
emits JSON detection events. It has no database, no auth layer, and no
persistent state beyond log files.

Two independent ML engines run side by side:

- **Sound detection** — TensorFlow Lite [YAMNet](https://www.kaggle.com/models/google/yamnet/tfLite)
  audio classifier (`tflite-support` / `tflite-runtime`) over ~500 sound classes.
- **Wake word detection** — [PocketSphinx](https://pocketsphinx.readthedocs.io/)
  keyword spotting with per-language CMU Sphinx acoustic models (`fr`, `en`).

---

## 2. Non-negotiable rules

1. **Python 3.11 only.** Do not add 3.12+ syntax. Note both ruff configs say
   `target-version = "py312"` despite `requires-python` — a pre-existing
   inconsistency; do not "fix" it by lowering the language floor.
2. **Configure via environment variables, never CLI flags** for anything you
   want to take effect at runtime. See [section 7](#7-the-cli-is-inert-read-this).
3. **Indent with 2 spaces.** `.editorconfig` and the effective ruff config both
   enforce `indent_size = 2`. 4-space Python is wrong here.
4. **Never call `ruff check .` casually.** The effective config has `fix = true`
   (see [section 11](#11-code-style-and-conventions)); a bare check silently
   rewrites files. Use `ruff check . --no-fix` to inspect.
5. **Never run pre-commit on all files.** `.continuerules` is explicit: only on
   changed files.
6. **Every `.py` file needs the 14-line Apache-2.0 header** from
   `LICENSE_HEADER.txt` (see any existing file for the exact shape, including
   the trailing `# ====...====` separator line).
7. **Do not edit build artifacts:** `dist/`, `public/`, `.venv/`, `.devbox/`,
   `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`, `__pycache__/`.
   `public/` and `dist/` are gitignored and generated.
8. **Do not add `conftest.py`.** This repo has none; tests are self-contained by
   convention. See [section 10](#10-testing).
9. **Tests must pass from the repo root** and they load real model files — see
   [section 10](#10-testing). A green run is not optional.
10. **Never commit `*.tflite`.** `.gitignore` excludes them; `models/yamnet.tflite`
    must be fetched, not committed.

---

## 3. Repository map

```
.
├── ohunerin/                     # the installable package (2,260 LOC)
│   ├── __init__.py               # public API + main()/start() bootstrapping
│   ├── __main__.py               # `python -m ohunerin` shim
│   ├── audio/
│   │   └── processing.py         # to_ndarray(): int16 PCM -> normalized float64
│   ├── core/                     # PEP 420 namespace pkg (no __init__.py)
│   │   ├── args.py               # argparse definition  (⚠ parsed, then discarded)
│   │   ├── events.py             # generic async EventManager
│   │   ├── logger.py             # console + rotating-file logging setup
│   │   ├── package.py            # APP_NAME/VERSION + DEFAULT_* paths (reads pyproject.toml)
│   │   └── settings.py           # pydantic-settings Settings + config.json merging
│   ├── engines/                  # PEP 420 namespace pkg
│   │   ├── detector.py           # DetectorEngine (YAMNet) + DetectorConsumer (buffering)
│   │   └── wakeword.py           # WakewordEngine (PocketSphinx KWS)
│   ├── models/                   # PEP 420 namespace pkg
│   │   ├── sound.py              # SUPPORTED_SOUNDS (500+ labels), SoundsConfig, DetectedSound
│   │   └── wakeword.py           # WakewordEntry, WakewordSetting, WakewordsConfig
│   └── server/
│       ├── __init__.py           # Server: HTTP routing, WS session, detection loop
│       ├── http.py               # HttpHandler: /health, /api/sounds, /openapi.json, /docs
│       └── websocket.py          # WebSocketServer ABC + BroadcastingWebSocketServer
├── tests/                        # 12 files, 61 tests, no conftest.py
├── models/                       # CMU Sphinx models (tracked) + yamnet.tflite (untracked)
│   ├── wakeword-en/{acoustic-model/,pronounciation-dictionary.dict}
│   ├── wakeword-fr/{cmusphinx-fr-ptm-8khz-5.2/,pronounciation-dictionary.dict}
│   └── yamnet.tflite             # 4.1 MB, gitignored, fetched by scripts/install-model.sh
├── htdocs/                       # served statically: index.html (Scalar) + openapi.json
├── config.json                   # bundled default wakewords + sounds config
├── client.py                     # reference microphone client (sounddevice + websockets)
├── bin/
│   ├── oremi-ohunerin            # sh wrapper -> python -m ohunerin
│   └── entrypoint.sh             # Docker ENTRYPOINT
├── scripts/install-model.sh      # downloads yamnet.tflite
├── Dockerfile                    # 2-stage, python:3.11-slim, port 5023
├── Makefile                      # dev/test/package/release targets
├── pyproject.toml                # hatchling build, deps, pytest + (dead) ruff config
├── ruff.toml                     # EFFECTIVE ruff config (overrides pyproject)
├── .pylintrc                     # pylint config (legacy, 11 KB)
├── tox.ini                       # flake8/pycodestyle/pydocstyle settings only
├── bandit.yaml                   # security-lint skips
├── .hadolint.yaml                # Dockerfile lint skips (DL3008)
├── .pre-commit-config.yaml       # prek/pre-commit hooks (excludes tests/)
├── devbox.json / devbox.lock     # pinned Nix toolchain
└── .gitlab-ci.yml                # SAST + GitLab Pages  (⚠ deploy job is broken)
```

**Namespace packages:** only `ohunerin/__init__.py` and
`ohunerin/server/__init__.py` exist. `core/`, `engines/`, `models/`, `audio/` are
implicit PEP 420 namespace packages. Do not add `__init__.py` to them without a
reason — it changes packaging behavior.

---

## 4. Architecture and control flow

```
                       env: OREMI_OHUNERIN_*        config.json
                                     │                   │
                                     ▼                   ▼
  oremi-ohunerin ──► ohunerin.main() ──► start() ──► Settings  (pydantic-settings)
   (console script)                        │            │
                                           │            ├─ wakewords_config: WakewordsConfig
                                           │            └─ sounds_config:    SoundsConfig
                                           ▼
                                        Server(WebSocketServer)
                                           ├─ HttpHandler ──► GET /, /health, /openapi.json,
                                           │                  /docs, /api/sounds
                                           │                  (returns None for /ws → upgrade)
                                           └─ listen(host, port)
                                                 │
                        ┌────────────────────────┴────────────────────────┐
                        ▼                                                 ▼
                 HTTP request                              WebSocket connection
              (process_http_request)                       (_handle_messages)
                                                                          │
                                                              _parse_query_params(path)
                                                                          │
                                             ┌────────────────────────────┴───────────┐
                                             ▼                                        ▼
                                  WakewordEngine (per language)            DetectorConsumer (per connection)
                                   run_in_executor(ThreadPool)              run_in_executor(ThreadPool)
                                             │                                        │
                                             │                          DetectorEngine (shared, locked)
                                             │                                        │
                                             └────────────► JSON detection events ◄────┘
                                                          websocket.send(...)
```

Boot sequence — `ohunerin/__init__.py::start()`:

1. `parse_arguments()` — result is **thrown away** (see section 7).
2. Read `OREMI_OHUNERIN_LOG_LEVEL` / `OREMI_OHUNERIN_LOG_FILE` **directly from
   `os.environ`** and call `configure_logging()`. Note this bypasses
   `Settings.log_level`, which is effectively display-only.
3. Construct `Settings()` → resolves config, models, TLS paths, validates the
   model file exists.
4. Log the resolved groups via `log_group()` / `log_config_details()`.
5. Construct `Server(...)` and `await server.listen(host, port)`.

`Server.__init__` calls `asyncio.get_running_loop()`, so **`Server` must be
constructed inside a running event loop.** Tests respect this with
`@pytest_asyncio.fixture`.

### Per-chunk detection loop

`Server._handle_audio_data()` is the hot path:

```
for each binary frame:
    if wakeword_engine:
        sound, score = await run_in_executor(pool, wakeword_engine.process_raw, chunk)
        if sound:
            send {"type": "wakeword", ...}
            detector_consumer.reset_buffer()
            continue          # ← sound detection is SKIPPED for this chunk
    if detector_consumer:
        sound, score = await run_in_executor(pool, detector_consumer.process_raw, chunk)
        if sound:
            send {"type": "sound", ...}
```

Three things worth internalizing before you touch this:

- **Both engines run in the thread pool.** Sound detection used to call
  `DetectorConsumer.process_raw` inline, which blocked the event loop for the
  whole inference (measured: 185 ms/window with the old default thread count).
  It now goes through `run_in_executor` like wake word, at the cost of roughly
  10-35% single-engine throughput. Reverting it re-introduces the stall; see
  [section 14](#14-concurrency-and-lifecycle-constraints).
- **The detector engine is shared, the consumer is not.** `HttpHandler.get_detector_engine()`
  is `@lru_cache`d (one TFLite interpreter for the process) and
  `DetectorEngine.classify_window()` serializes access with a `threading.Lock`.
  `HttpHandler.get_detector_consumer()` returns a **new** `DetectorConsumer` per
  call, so each connection owns its 15,600-byte window buffer.
- **When a wake word fires, that chunk is not also classified as a sound.** The
  `continue` is deliberate (the buffer was just reset).

---

## 5. Runtime contracts you must not break

### 5.1 Audio wire contract

| Property        | Value                                                                     |
| --------------- | ------------------------------------------------------------------------- |
| Direction       | Client → server: binary WebSocket frames                                  |
| Encoding        | Raw PCM, signed 16-bit little-endian, mono                                |
| Sample rate     | 16,000 Hz                                                                 |
| Detector window | exactly **15,600 bytes** (`DetectorConsumer._buffer`)                     |
| Normalization   | `to_ndarray()` → `int16 / 32768.0` → `float64`, reshaped `(-1, channels)` |

A session must stream continuously from the start of the connection: the
consumer counts bytes, not timestamps, so the window is not aligned to the
client's block boundaries. `client.py` streams `blocksize=4000` samples
(8,000 bytes); the detector only classifies once its 15,600-byte buffer fills,
and any remainder carries over to the next frame.

### 5.2 WebSocket session contract

Endpoint: **`/ws`** exactly. Any other path is closed with **1008**.

Query parameters:

| Param      | Required                 | Values                                                                      |
| ---------- | ------------------------ | --------------------------------------------------------------------------- |
| `features` | yes                      | CSV of `wakeword-detection`, `sound-detection`. Unknown values are ignored. |
| `language` | iff `wakeword-detection` | Must be a language present in `config.json` (currently `fr`, `en`).         |

Invalid `features`/`language` → `ValueError`, surfaced as close **1003**.

Close codes actually emitted:

| Code | Cause                                                 | Source                |
| ---- | ----------------------------------------------------- | --------------------- |
| 1003 | bad query params, processing error, no usable feature | `server/__init__.py`  |
| 1008 | path is not `/ws`                                     | `server/__init__.py`  |
| 4000 | unexpected error in the socket handler                | `server/websocket.py` |

Close reasons are truncated by `Server.truncate_reason()` to `MAX_REASON_LENGTH = 123`
(120 chars + `"..."`). Keep new reason strings short.

### 5.3 Detection event schema

Every detection emits one JSON text frame shaped by
`create_detected_sound_object()` in `ohunerin/models/sound.py`:

```json
{
  "type": "sound" | "wakeword",
  "sound": "<label or wake word>",
  "score": 0.109375,
  "datetime": "2023-08-16T14:42:46.424809"
}
```

`datetime` is naive local time via `datetime.datetime.now().isoformat()`. Labels
for `"type": "sound"` are lowercased (`sound.category_name.lower()`), so they do
**not** match the capitalized entries in `SUPPORTED_SOUNDS`.

### 5.4 HTTP contract

| Route           | Response                                                                                              |
| --------------- | ----------------------------------------------------------------------------------------------------- |
| `/`             | 302 → `/health`                                                                                       |
| `/health`       | `{name, version, threshold, wakewords: {lang: [words]}, sounds: {allowlist, denylist}}`, CORS `*`     |
| `/api/sounds`   | JSON array = `SoundsConfig.effective_allowlist`, CORS `*`                                             |
| `/openapi.json` | `htdocs/openapi.json` with `info.description` ← `DOCUMENTATION.md` and `info.version` ← `APP_VERSION` |
| `/docs`         | `htdocs/index.html` (Scalar API reference)                                                            |
| `/ws`           | returns `None` → websockets performs the upgrade                                                      |
| anything else   | 404, `text/plain`, body `Not Found`                                                                   |

`htdocs/openapi.json` is read from disk **once at import time**
(`SERVICE_DESCRIPTION` in `server/http.py`), so editing `DOCUMENTATION.md`
requires a process restart to show up on `/docs`.

---

## 6. Configuration

### 6.1 Environment variables

All settings use the `OREMI_OHUNERIN_` prefix (`SettingsConfigDict`). This is the
**only** mechanism that actually changes runtime behavior.

| Variable                     | Type                                            | Code default                  | Effect                                 |
| ---------------------------- | ----------------------------------------------- | ----------------------------- | -------------------------------------- |
| `OREMI_OHUNERIN_SERVER_HOST` | str                                             | `127.0.0.1`                   | bind address                           |
| `OREMI_OHUNERIN_SERVER_PORT` | int 1–65535                                     | `5023`                        | bind port                              |
| `OREMI_OHUNERIN_CONFIG_PATH` | path                                            | bundled `config.json`         | see fallback below                     |
| `OREMI_OHUNERIN_MODEL_PATH`  | path                                            | `<repo>/models/yamnet.tflite` | **must exist** or startup fails        |
| `OREMI_OHUNERIN_THRESHOLD`   | float 0–1                                       | `0.1`                         | YAMNet score cutoff                    |
| `OREMI_OHUNERIN_CERT_FILE`   | path                                            | `None`                        | enables TLS                            |
| `OREMI_OHUNERIN_KEY_FILE`    | path                                            | `None`                        | TLS private key                        |
| `OREMI_OHUNERIN_PASSWORD`    | str                                             | `None`                        | private-key password (blank → `None`)  |
| `OREMI_OHUNERIN_LOG_LEVEL`   | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR`\|`CRITICAL` | `INFO`                        | read from `os.environ`, not `Settings` |
| `OREMI_OHUNERIN_LOG_FILE`    | path                                            | `None` (stderr)               | 5 MB × 5 rotating file                 |

`.env.example` is the copy-paste template. Note `Settings.model_config` sets
`strict=True`, but pydantic-settings still coerces env strings
(`OREMI_OHUNERIN_SERVER_PORT=1234` → `int`). Verified — do not "fix" that.

### 6.2 `config.json`

One unified file (the old `wakeword.json` / `sounds.json` split was removed).
Shape is documented as TypeScript interfaces in `DOCUMENTATION.md`.

```jsonc
{
  "wakewords": [
    {
      "language": "fr", // BCP-47 code; must match a model dir
      "word": "oremi",
      "phones": ["oo rr ei mm ii", "oo rr ai mm ii"], // PocketSphinx phones, NOT IPA
      "discriminants": [
        // optional false-positive guards
        { "word": "remi", "phones": ["rr ei mm ii"] },
      ],
    },
  ],
  "sounds": { "allowlist": [], "denylist": [] },
}
```

Rules enforced by `ohunerin/models/sound.py` and `ohunerin/models/wakeword.py`:

- `sounds.allowlist` non-empty → **denylist is ignored**. Both empty → all
  supported labels are allowed.
- Every label must be a member of `SUPPORTED_SOUNDS`; otherwise validation fails
  with a `ValueError` that lists **all** valid labels. Duplicates are dropped
  (order-preserving).
- `phones` strings are space-separated PocketSphinx phoneme sequences. Multiple
  entries = multiple accepted pronunciations. Phone inventories differ per
  language model.
- `WakewordsConfig` and `SoundsConfig` both accept loose input
  (`WakewordsConfig` wraps a bare list or single dict; `Settings.config` wraps a
  top-level JSON list as `{"wakewords": [...]}`).

### 6.3 Precedence and fallbacks (verified behavior)

1. If `OREMI_OHUNERIN_CONFIG_PATH` points at a **file that does not exist**, it is
   silently replaced by the bundled `config.json`. No warning is logged.
2. If the resolved file parses to an empty/partial dict, each missing top-level
   section (`wakewords`, `sounds`) is filled in **individually** from the bundled
   default.
3. **Malformed JSON raises `ValueError` lazily** — on first access to
   `Settings.config` (a `cached_property`), not at `Settings()` construction.
4. `Settings.model_path` is validated eagerly and raises
   `ValidationError: Model file does not exist: ...` — a missing model is a hard,
   fast startup failure.
5. `wakewords_config` / `sounds_config` are `cached_property` values; the JSON is
   read once per `Settings` instance.

---

## 7. The CLI is inert (read this)

`ohunerin/core/args.py` defines a full `argparse` surface (`-c/--config`,
`--host`, `-p/--port`, `--cert-file`, `--key-file`, `--password`, `-v/--version`).
`DOCUMENTATION.md` documents all of it. But:

```python
async def start() -> None:
  parse_arguments()          # ← return value is discarded
  ...
  settings = Settings()      # ← everything comes from env vars
```

**No CLI flag except `--version` and `--help` has any runtime effect.** Passing
`--port 8080` will still bind `OREMI_OHUNERIN_SERVER_PORT` or 5023.

This is the single most likely trap in the repo. If a user reports "the port
flag does nothing", that is the expected behavior, not a bug you introduced.

Before "fixing" it, know the blast radius: `bin/entrypoint.sh`, `.vscode/launch.json`,
and the `Dockerfile` ENV block all pass flags that are currently ignored, and
`tests/test_args.py` asserts only the parser's own output. Wiring args into
`Settings` is a real behavior change and needs its own tests plus doc updates.

---

## 8. Development environment

Two supported setups (see `CONTRIBUTING.md`): Dev Containers and devbox + direnv.
The devbox path is the one that works from a terminal:

```sh
direnv allow          # loads devbox env via .envrc
make install          # ⚠ rm -rf .venv, then uv venv --python 3.11 && uv sync
make model            # ⚠ currently a no-op; download yamnet.tflite manually
```

Notes:

- `.venv/` is Python 3.11.12 and has `oremi-ohunerin` installed **editable**
  (`_editable_impl_oremi_ohunerin.pth`), so `import ohunerin` resolves to the
  working tree. That is why local imports and `pyproject.toml` reads work.
- `make install` deletes `.venv` first. Do not run it casually if the venv is
  already set up.
- `make model` depends on `$(TSLITE_FILE)`, which **is defined nowhere** in the
  repo. `make model` prints "Nothing to be done". Fetch the model directly:

  ```sh
  ./scripts/install-model.sh models/yamnet.tflite
  ```

- **`uv` is not on the plain PATH** — it lives in
  `.devbox/nix/profile/default/bin` (or through `devbox run`). Same for `ruff`,
  `hadolint`, `editorconfig-checker`, `prek`, `twine`, `uvx`.
- **`uv run` fails out of the box** in restricted environments because it needs a
  writable cache at `~/.cache/uv`. Point it inside the workspace:

  ```sh
  export PATH="$PWD/.devbox/nix/profile/default/bin:$PATH"
  mkdir -p .tmp/uvcache
  UV_CACHE_DIR="$PWD/.tmp/uvcache" uv run pytest tests/ -q
  ```

- **`mypy` is not installed anywhere** (not in `.venv`, not in devbox), even
  though `.pre-commit-config.yaml` runs `mypy --strict`. That gate cannot be
  executed locally as configured.
- `pylint`, `bandit`, `autopep8` ARE in `.venv/bin`. Use `.venv/bin/python -m pylint …`.

---

## 9. Commands that actually work

Run everything from the repository root.

### Test

```sh
.venv/bin/python -m pytest tests/ -q          # → 61 passed in ~1.5 s  ✅ verified
```

Alternative when `uv` is on PATH:

```sh
UV_CACHE_DIR="$PWD/.tmp/uvcache" uv run pytest tests/ -q   # ✅ verified
```

`make tests` = `uv run pytest tests/ -v` — will fail without the `UV_CACHE_DIR`
workaround. Coverage: `make coverage` uses `--cov=server`, but **no top-level
`server` package exists** (it is `ohunerin.server`), so the coverage targets
report nothing. Use `--cov=ohunerin` instead.

### Lint / static analysis

```sh
export PATH="$PWD/.devbox/nix/profile/default/bin:$PATH"

ruff check . --no-fix --statistics      # inspect only (fix=true would rewrite!)
ruff check .                            # ⚠ AUTO-FIXES files
hadolint Dockerfile                     # ✅ clean
editorconfig-checker                    # ✅ clean
.venv/bin/python -m bandit -c bandit.yaml -r ohunerin -q   # ✅ clean
.venv/bin/python -m pylint --rcfile=.pylintrc ohunerin     # 9.85/10
```

Current baseline: ruff reports exactly one issue —
`tests/test_models.py:22:96: F401 WakewordSetting imported but unused`.
Leaving it is acceptable; fixing it is a one-line change. pylint's only finding
is shared `__all__` duplicate-code between `ohunerin/__init__.py` and
`ohunerin/server/__init__.py`.

### Benchmark

`benchmarks/` holds three standalone scripts (no pytest, no conftest). They all
need `models/yamnet.tflite`:

```sh
.venv/bin/python benchmarks/bench_pipeline.py --threads 4   # per-stage micro-benchmarks
.venv/bin/python benchmarks/bench_wakeword.py              # PocketSphinx cost + RSS
.venv/bin/python benchmarks/bench_server.py --connections 4 --windows 6 --threads 0
.venv/bin/python benchmarks/bench_server.py --threads 0 --legacy-inline   # pre-optimization path
```

`bench_server.py` reports throughput and event-loop scheduling lag;
`--threads 0` uses `recommended_num_threads()`, `--legacy-inline` reproduces the
old loop that ran inference on the event loop, and `--json` emits machine-readable
output. Use `--legacy-inline` for controlled before/after comparisons.

### Run the server locally

```sh
OREMI_OHUNERIN_SERVER_HOST=127.0.0.1 \
OREMI_OHUNERIN_SERVER_PORT=5023 \
OREMI_OHUNERIN_LOG_LEVEL=DEBUG \
.venv/bin/python -m ohunerin
```

Smoke checks:

```sh
curl -s localhost:5023/health | python -m json.tool
curl -s localhost:5023/api/sounds | head -c 200
```

Microphone client (needs a real input device):

```sh
python client.py --list-devices
python client.py --host localhost --port 5023 --language fr
```

`make client` runs `uv add --dev sounddevice` first, which **mutates
`pyproject.toml` and `uv.lock`.** Prefer invoking `client.py` directly.

### Package / release

```sh
make package     # uv build --wheel + twine check   (reads dist/)
make image       # docker buildx → demsking/oremi-ohunerin (linux/amd64, --push)
make image-test  # local docker build only
make beta | patch | minor | major   # version bump helpers (require clean tree)
make release     # commit + annotated tag
make publish     # pypi + image + push main and tag
```

`make beta`/`patch`/`minor`/`major`/`release`/`publish` all depend on
`check-clean`, which fails if `git status --porcelain` is non-empty. Commit first.

---

## 10. Testing

**61 tests across 12 files. No `conftest.py` anywhere. No `tests/__init__.py`.**

| File                          | Tests | Needs real models?              |
| ----------------------------- | ----- | ------------------------------- |
| `test_args.py`                | 2     | no                              |
| `test_audio.py`               | 3     | no                              |
| `test_detector.py`            | 4     | **yes**                         |
| `test_detector_pipeline.py`   | 8     | **yes**                         |
| `test_event_manager.py`       | 2     | no                              |
| `test_init.py`                | 5     | no (`Server`/`Settings` mocked) |
| `test_models.py`              | 9     | no                              |
| `test_server.py`              | 2     | **yes**                         |
| `test_server_audio_loop.py`   | 9     | **yes**                         |
| `test_server_query_params.py` | 10    | **yes**                         |
| `test_settings.py`            | 4     | **yes**                         |
| `test_wakeword.py`            | 3     | **yes**                         |

### Hard prerequisites

Tests are **integration-flavored**: heavy native dependencies are never stubbed.
`tests/` never imports `tflite_support`, `pocketsphinx`, or `sounddevice`
directly, but the modules under test do, and the engines load real artifacts:

- `models/yamnet.tflite` — **untracked** (matches `.gitignore *.tflite`). A fresh
  clone must run `./scripts/install-model.sh models/yamnet.tflite` first.
  Measured: without it the suite goes from `61 passed` to
  **`14 failed, 46 passed, 1 error`** (`test_detector`,
  `test_detector_pipeline`, `test_server`, `test_server_query_params`,
  `test_server_audio_loop`, `test_settings`).
- `models/wakeword-{en,fr}/…` — tracked, present in a normal clone.
- `config.json` — tracked, at the repo root.
- Tests resolve paths from `__file__` **and** from the current working directory,
  so they must run from the repo root.

### Conventions to copy

1. **No shared fixtures.** Each file defines its own `@pytest.fixture def logger()`
   (a bare `logging.getLogger("test_x")`, often unused) and its own model/config
   fixture. Do not introduce `conftest.py`.
2. **License header + 2-space indent** in every new test file, matching the
   existing 14-line header and `# ====…====` separator.
3. **Imports:** one symbol per line, stdlib → third-party → `ohunerin.*`, with a
   blank line between groups. `I` is not selected by the effective ruff config,
   so ordering is not enforced, but match the surrounding style.
4. **Import the package directly** (`from ohunerin.server import Server`). No
   `sys.path` hacks — the editable install handles it.
5. **Async:** `pyproject.toml` sets `asyncio_mode = "auto"`, yet async tests still
   carry an explicit `@pytest.mark.asyncio` and async fixtures use
   `@pytest_asyncio.fixture`. Follow the existing pattern.
6. **Mocking:** `unittest.mock` only. Two idioms in use:
   - `MagicMock(side_effect=[(None, 0.0), ("oremi", 0.95)])` for `process_raw`.
   - `patch.object(server, "_handle_audio_data", side_effect=async_fn)` for the
     async detection loop.
     Class-level: `patch("ohunerin.parse_arguments", …)`, `patch("ohunerin.Settings", …)`,
     `patch("ohunerin.Server", …)`. Never patch native libraries.
7. **A `MockWebSocket` class is the standard fake connection** — see
   `tests/test_server_audio_loop.py:31-57`. It implements `__aiter__`/`__anext__`,
   `send`, `close`, and records `sent_messages`, `closed_code`, `closed_reason`.
   `server.path` is set explicitly per test. Reuse this shape; do not invent
   another fake or spin a real socket.
8. **Temp config files:** `tempfile.NamedTemporaryFile("w+", delete=False)` plus
   `try/finally: os.unlink(...)`. The `tmp_path` pytest fixture is unused in this
   repo — prefer matching the existing idiom.
9. **The `Server` fixture must be async** (`@pytest_asyncio.fixture`) because
   `Server.__init__` calls `asyncio.get_running_loop()`.
10. **`# type: ignore` is used freely** on private-attribute access in tests;
    that is consistent with the codebase.

### Adding a test — checklist

- [ ] New file starts with the license header; 2-space indent.
- [ ] Paths derived from `Path(__file__).resolve().parents[1]`, never hardcoded.
- [ ] If it touches a real engine, note the `yamnet.tflite` prerequisite in a comment.
- [ ] `.venv/bin/python -m pytest tests/ -q` still shows `61 + N passed`.
- [ ] No `conftest.py`, no `monkeypatch`, no new mock library.

---

## 11. Code style and conventions

### The effective ruff config is `ruff.toml`, not `pyproject.toml`

Verified with `ruff check --show-settings`:

```
Settings path: "/home/…/oremi-ohunerin/ruff.toml"
```

A root `ruff.toml` **silently overrides** `[tool.ruff]` in `pyproject.toml`.
Consequences — `pyproject.toml`'s `[tool.ruff]` block is **dead configuration**:

| Setting          | Effective (`ruff.toml`)   | Dead (`pyproject.toml`) |
| ---------------- | ------------------------- | ----------------------- |
| `line-length`    | **128**                   | 120                     |
| `indent-width`   | 2                         | 2                       |
| `select`         | **E, F, W, RUF**          | E, F, I, UP, B          |
| `fix`            | **true**                  | —                       |
| quotes           | inline `'`, docstring `"` | —                       |
| `target-version` | py312                     | py312                   |

So: `I` (import sorting), `UP` (pyupgrade), and `B` (bugbear) are **not
enforced**, and `E501` (line too long) is ignored. If you want a rule enforced,
edit `ruff.toml` — or delete one of the two files. Do not add rules to
`pyproject.toml` and assume they apply.

### Formatting rules

- **2-space indentation**, LF line endings, final newline, no trailing whitespace
  (`.editorconfig`, `.gitattributes`, ruff).
- Line length 128 hard-ish (E501 ignored, so long lines are tolerated; existing
  code has some very long lines — match local style rather than reflowing).
- Single quotes for inline strings, double quotes for docstrings.
- Type hints on all public functions; `from __future__` is not used (3.11 target
  is new enough for `X | None`).
- Docstrings are Google-style where present (see `DetectorConsumer.__init__`).
- `__all__` is declared in `ohunerin/__init__.py`, `ohunerin/server/__init__.py`,
  `engines/*.py`, `audio/processing.py`.

### Module conventions

- Module-level `logger = logging.getLogger(__name__)` in every module.
- `if TYPE_CHECKING` is not used; imports are direct.
- New public symbols are re-exported from `ohunerin/__init__.py` **and**
  `ohunerin/server/__init__.py` where relevant. Keep both `__all__` lists in sync
  — pylint's only finding today is duplicate code between those two lists.

### License headers

`.pre-commit-config.yaml` runs `insert-license` with
`--license-filepath LICENSE_HEADER.txt --use-current-year`. New files get the
current year; existing files keep their ranges (e.g. `2023-2026`). Copy an
existing header verbatim and adjust nothing but the year if needed.

**Caveat:** `.pre-commit-config.yaml` has a global `exclude: ^(tests)/.*`, so
**no hook runs on `tests/`** — including the license-header hook. Tests still
have headers; add them by hand.

### Stale rule file

`.continuerules` says "Whenever you are writing code, make sure to use
**TypeScript** typing." This is a leftover from a Cursor setup and is wrong for
this Python repository. It also says "Never call pre-commit on all files, only
on changed files" — that part is valid and applies here.

---

## 12. Git and commit conventions

The project uses **Conventional Commits** with lowercase types and scopes,
present-tense imperative subjects:

```
<type>(<scope>): <lowercase imperative subject>
```

Types observed across 168 commits: `chore` (16), `refactor` (13), `feat` (7),
`docs` (7), `fix` (5), `style` (3), `build` (3), `test` (1).

Frequently used scopes: `release`, `config`, `server`, `protocol`, `logging`,
`pre-commit`, `docker`, `deps`, `docs`, `wakeword`, `sound`, `openapi`,
`packaging`, `types`, `tests`.

Examples from history:

```
feat(logging): add structured HTTP access logging and clean up loggers
fix(logging): improve exception handling in main entrypoint
refactor(config): unify configuration into single config.json
chore(release): bump version to 4.0.0b10
docs(license): expand Apache 2.0 license notice with full boilerplate
```

Other requirements:

- **Branch:** `main` only. `origin/HEAD → origin/main`. There is no `dev` branch.
- **Version bumps** go through `make beta|patch|minor|major`, which run
  `uv version` and `uv lock`. Never hand-edit the version in `pyproject.toml`
  without also regenerating `uv.lock`.
- Release commits are generated: `chore(release): bump version to X`.
- `make release` creates an annotated tag `v<version>`.
- Keep `pyproject.toml` and `uv.lock` in the same commit.

---

## 13. Known traps and stale artifacts

Everything below was verified against the working tree. Treat the listed files as
**unreliable documentation** and prefer the source.

### 13.1 Packaging is broken for `pip install`

`DOCUMENTATION.md` advertises `pip install oremi-ohunerin` /
`uv tool install oremi-ohunerin`. **That path does not work.**

`ohunerin/core/package.py` reads `pyproject.toml` at _import time_:

```python
PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]
with (PROJECT_DIRECTORY / "pyproject.toml").open("rb") as file:
    ...
```

Installed into `site-packages/`, `parents[2]` is `site-packages`, and the built
wheel contains **no `pyproject.toml`**. Verified reproduction: copying `ohunerin/`
to a directory without `pyproject.toml` and importing it yields

```
FileNotFoundError: [Errno 2] No such file or directory: '/tmp/simsp/pyproject.toml'
```

Additional wheel gaps (inspected `dist/oremi_ohunerin-4.0.0b10-py3-none-any.whl`,
42 entries):

- `models/yamnet.tflite` — **absent** (hatchling honors `.gitignore`, where
  `*.tflite` is listed) → even with `pyproject.toml`, `Settings` would raise
  `Model file does not exist`.
- `config.json` — **absent**, despite being tracked.
- `pyproject.toml` — **absent**.
- Present: `ohunerin/**`, `htdocs/**`, the CMU Sphinx models, `LICENSE`,
  `DOCUMENTATION.md`.

`pyproject.toml` `[tool.hatch.build.targets.wheel].packages` still lists
`wakeword.json` and `sounds.json`, **both deleted** in commit `f49635f`
(config was unified into `config.json`). It also omits `config.json`.

The **Docker image works** only because the Dockerfile copies the source tree to
`/oremi` and sets `PYTHONPATH=/oremi`, so `/oremi/pyproject.toml` exists.

If you are asked to fix installation, the minimal correct fix is to stop reading
`pyproject.toml` at import time (bake `__version__` into the package or use
`importlib.metadata`) and to add `config.json` + the model to the wheel data.

### 13.2 `.gitlab-ci.yml` deploy job is broken

The `pages` job copies and runs four paths that **do not exist**:

| Line | Reference                                      | Status                          |
| ---- | ---------------------------------------------- | ------------------------------- |
| 31   | `integrations/home-assistant/oremi-ohunerin/*` | removed in `ead9675`            |
| 34   | `ohunerin/DOCUMENTATION.md`                    | moved to repo root in `7c7e732` |
| 34   | `ohunerin/doc/*`                               | never existed in this layout    |
| 35   | `scripts/generate_openapi.py`                  | deleted in `674a608`            |

Only the `sast` stage is dependable. Do not assume CI validates your change.

### 13.3 Makefile gaps

- `model:` depends on `$(TSLITE_FILE)`, **defined nowhere** → `make model` is a
  no-op. Consequently `make install` does not fetch `yamnet.tflite`.
- `coverage` / `coverage-html` use `--cov=server`; the package is `ohunerin`.
  Coverage reports are empty.
- `APP_VERSION := $(shell uv version --short)` and `$(shell uvx …)` run at parse
  time. Without the devbox PATH, every `make` invocation emits
  `uv: No such file or directory` noise even for unrelated targets.

### 13.4 Stale OpenAPI artifacts

- `public/openapi.json` is **untracked build output** (`/public` is gitignored)
  describing paths `/ws`, `/info`, `/sounds` — none of which exist anymore
  (real: `/health`, `/api/sounds`). Never edit or trust it. It is a leftover from
  the deleted `scripts/generate_openapi.py`.
- `htdocs/openapi.json` (the file actually served) has `info.version` pinned to
  `4.0.0b1`; the server overwrites it at runtime with `APP_VERSION`, so the file
  on disk is always stale.
- `htdocs/openapi.json` documents `/ws`, `/health`, `/api/sounds` but omits
  `/`, `/openapi.json`, and `/docs` — all of which the server implements.
- It documents close code **1007** for "no valid feature"; the server actually
  sends **1003** (`server/__init__.py`, the `wakeword_engine is None and
detector_consumer is None` branch).

### 13.5 Tests that pass but assert nothing real

`tests/test_server_query_params.py` and
`tests/test_server_audio_loop.py::test_handle_messages_valid_flow` exercise
`sounds=` and `allowlist=` query parameters — **`Server._parse_query_params`
never reads them.** It only reads `features` and `language`. Their docstrings
("intersected with the server's configured list", "unknown labels are silently
dropped") describe behavior that does not exist; the asserts are weak enough
(`dt_consumer is not None`) that they pass regardless.

A related comment claims `"Dog"` and `"Cat"` "are not in config.json sounds →
filtered out", but `config.json` has empty allowlist **and** denylist, meaning
_all_ labels are allowed.

If you implement per-session sound filtering, these tests become meaningful —
rewrite the assertions then.

### 13.6 Documentation divergences

| Claim                                                                                     | Reality                                                                       |
| ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `DOCUMENTATION.md`: `OREMI_OHUNERIN_SERVER_HOST` default `0.0.0.0`                        | code default is `127.0.0.1`; only the Dockerfile ENV sets `0.0.0.0`           |
| `DOCUMENTATION.md`: config default `/oremi/data/config.json`                              | code default is the bundled `<repo>/config.json`; `/oremi/...` is Docker-only |
| `DOCUMENTATION.md`: model default `/oremi/models/yamnet.tflite`                           | code default is `<repo>/models/yamnet.tflite`; Docker-only path               |
| `DOCUMENTATION.md`: full CLI reference                                                    | CLI flags are inert (section 7)                                               |
| `.env.example`: model default `~/.local/share/oremi-ohunerin/yamnet.tflite`               | no such path exists in code                                                   |
| `CONTRIBUTING.md`: "branch from the `dev` branch"                                         | there is no `dev` branch; only `main`                                         |
| `CONTRIBUTING.md` + `.vscode/settings.json` (`python.envFile`) reference `.devcontainer/` | `.devcontainer/` was deleted in `7c7e732`                                     |

### 13.7 Minor / cosmetic

- `tests/__pycache__/test_config.cpython-311-pytest-9.0.3.pyc` is an orphan:
  `tests/test_config.py` does not exist and was never tracked.
- `tests/*` define a `logger` fixture that most tests never use.
- `ohunerin/engines/detector.py::DetectorEngine.classify_window` logs the raw
  `sound` object at DEBUG (`logger.debug(sound)`).
- `client.py` uses the modern `websockets.asyncio.client.connect`, while the
  server uses the deprecated `websockets.legacy.server`. Both work against
  `websockets` 16.1.1, but `websockets.legacy` emits a `DeprecationWarning`.
- `pyproject.toml` dev group omits `ruff`, `mypy`, `hadolint` — they come from
  devbox only, which is why they are missing from `.venv`, and why `mypy` is
  simply unavailable.
- 3 warnings on every test run: an un-awaited `start` coroutine from
  `test_init.py`, plus the `websockets.legacy` deprecation. Pre-existing.

---

## 14. Concurrency and lifecycle constraints

Read this before touching anything connection-scoped.

**The sound path is concurrency-safe; the wake-word path is only partly so.**

`HttpHandler.get_detector_engine` is `@lru_cache`d (`ohunerin/server/http.py`) —
one TFLite interpreter for the process — and `DetectorEngine.classify_window`
serializes native access with a `threading.Lock`. `HttpHandler.get_detector_consumer`
is deliberately **not** cached: each call returns a fresh `DetectorConsumer`, so
every connection owns its own 15,600-byte window buffer. Concurrent
`sound-detection` connections are therefore correct.

The cost is that all inference funnels through one engine: measured ceiling
~330-435 windows/s per engine, and a 16 kHz connection needs ~2.05 windows/s, so
~160-210 concurrent sound connections saturate it. Beyond that, use a bounded
pool of engines (each ~8-11 MB) — do not raise the TFLite thread count, see
below.

`HttpHandler.get_wakeword_engine` keeps its `@lru_cache` (one `WakewordEngine`
per language, one PocketSphinx `Decoder`), and `WakewordEngine` now wraps every
decoder call in a `threading.Lock`. The lock prevents concurrent native state
mutation, but it does **not** give per-connection utterance isolation: two
clients on the same language still share one utterance stream and call
`end_utt()` on each other's audio, so their transcriptions can mix.

A decoder costs ~200 ms and ~22 MB to build, so unconditional per-connection
decoders are not viable at high fan-out. The realistic fixes, in order of
preference:

- a bounded per-language decoder pool, one decoder checked out per connection for
  the session's lifetime (queue or reject beyond the cap), or
- accept the shared stream, which is what the code does today.

Do **not** "fix" this by removing `@lru_cache` without measuring: construction is
expensive (TFLite ~8 ms / ~8-11 MB, PocketSphinx ~200 ms / ~22 MB), which is why
caching exists. Do not raise the TFLite `num_threads` either — see
`DEFAULT_MAX_INFERENCE_THREADS` in `engines/detector.py`.

Consequences:

- Do **not** describe the wake-word path as safely concurrent; the sound path is.
- Any concurrency change needs a test. `tests/test_detector_pipeline.py` covers
  per-connection consumer isolation, locked engine access, and the bounded thread
  count.

Other lifecycle facts:

- `Server.__init__` → `asyncio.get_running_loop()`; construct it inside a loop.
- `Server.pool` is a `ThreadPoolExecutor(max_workers=os.cpu_count())` created per
  `Server` and never shut down explicitly.
- `WebSocketServer.listen` awaits `asyncio.Future()` forever; teardown happens on
  cancellation via the `finally` block. There is no graceful-shutdown drain.
- `EventManager.trigger` swallows handler exceptions and logs them — a failing
  listener will not surface as a connection error.

---

## 15. Where to make a change

| Task                                             | Primary files                                                                                    |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| Add/change an HTTP route                         | `ohunerin/server/http.py` (`HttpHandler.process_request`)                                        |
| Change the WebSocket session rules / close codes | `ohunerin/server/__init__.py` (`_handle_messages`, `_parse_query_params`)                        |
| Change the per-chunk detection loop              | `ohunerin/server/__init__.py` (`_handle_audio_data`)                                             |
| Change the event JSON shape                      | `ohunerin/models/sound.py` (`create_detected_sound_object`) **+** `htdocs/openapi.json`          |
| Add/remove a supported sound label               | `ohunerin/models/sound.py` (`SUPPORTED_SOUNDS`)                                                  |
| Change config schema / validation                | `ohunerin/models/sound.py`, `ohunerin/models/wakeword.py`                                        |
| Change config loading, merging, fallbacks        | `ohunerin/core/settings.py`                                                                      |
| Add a setting                                    | `ohunerin/core/settings.py` **+** `.env.example` **+** `Dockerfile` ENV **+** `DOCUMENTATION.md` |
| Add/change a CLI flag                            | `ohunerin/core/args.py` — and see section 7 before expecting any effect                          |
| Change wake-word phoneme handling                | `ohunerin/engines/wakeword.py`, `config.json`                                                    |
| Change the YAMNet buffering/inference            | `ohunerin/engines/detector.py`                                                                   |
| Change audio decoding                            | `ohunerin/audio/processing.py`                                                                   |
| Change logging format/rotation                   | `ohunerin/core/logger.py`                                                                        |
| Change wake words or languages                   | `config.json`                                                                                    |
| Add a language                                   | `config.json` + `models/wakeword-<lang>/` + `LANGUAGE_MODEL_PATHS` in `ohunerin/server/http.py`  |
| Update the docs site content                     | `DOCUMENTATION.md` (also served as the OpenAPI description) + `htdocs/index.html`                |
| Update the API spec                              | `htdocs/openapi.json` (never `public/openapi.json`)                                              |

When adding a language, `LANGUAGE_MODEL_PATHS` in `server/http.py` has hardcoded
entries for `fr` and `en` with a generic fallback
(`wakeword-<lang>/acoustic-model` + `pronounciation-dictionary.dict`). Note the
misspelling `pronounciation` — it is the real on-disk filename; do not correct it
without renaming the files.

---

## 16. Definition of done

Before you report a change as complete:

1. **Tests:** `.venv/bin/python -m pytest tests/ -q` → all pass (baseline 61).
   Add tests for new behavior; follow section 10's conventions exactly.
2. **Lint:** `ruff check . --no-fix` introduces no _new_ findings (baseline: 1
   pre-existing `F401` in `tests/test_models.py`). If you run plain `ruff check .`,
   re-read your diff — it auto-fixed.
   Also consider `hadolint Dockerfile` (if touched) and
   `editorconfig-checker` (2-space indent, LF, final newline).
3. **Security:** `.venv/bin/python -m bandit -c bandit.yaml -r ohunerin -q` stays clean.
4. **Types:** there is no runnable mypy. If you changed signatures, at least keep
   hints accurate and consistent with call sites — `# type: ignore` is used
   where the native libs are untyped.
5. **Docs:** if you changed a setting, route, close code, CLI flag, or config
   field, update `DOCUMENTATION.md` and/or `htdocs/openapi.json`. Do not touch
   `public/`.
6. **Version:** only bump via `make beta|patch|minor|major` (it updates
   `uv.lock` too). Feature work on a pre-release stays in the `4.0.0bN` line.
7. **Commit:** conventional-commit format, narrow scope, no artifact commits
   (`dist/`, `public/`, `*.tflite`, `.venv/`, caches).
8. **Working tree:** `git status --porcelain` clean apart from your intended
   changes — several Makefile targets (`check-clean`) refuse to run otherwise.

---

## 17. Open questions — verify before assuming

Things this file could not settle from the source alone. Confirm empirically
before building on them:

- **YAMNet window size — RESOLVED.** Verified against `tflite-support` 0.4.4:
  `AudioClassifier.required_input_buffer_size` is **15,600 samples** (31,200
  bytes) at 16 kHz mono, and `TensorAudio` allocates a persistent `(15600, 1)`
  float32 buffer. `DetectorConsumer` accumulates only 15,600 *bytes* (7,800
  samples) per call, and `TensorAudio.load_from_array` *slides* that buffer left
  by 7,800 samples before appending, so the model always sees
  `[previous window, current window]` = 0.975 s, half of it one detection cycle
  old. Do not change the 15,600-byte constant without deciding whether that
  sliding behaviour is intended.
- **`is_discriminant` heuristics.** It flags any hypothesis containing a space
  whose two halves are equal (`"hello hello"` → discriminant) _and_ any
  configured discriminant word. Intent beyond that is undocumented.
- **Real-world throughput.** Measured — see the `benchmarks/` scripts and
  section 14. One engine sustains ~330-435 windows/s with ~1-4 ms event-loop lag.
  Re-measure after any change to the pool, the engine lock, or the executor.
- **PocketSphinx `kws_threshold`.** Hardcoded to `1e-10` in
  `engines/wakeword.py`; not configurable and not documented as tunable.
- **CI.** The GitLab Pages job is broken (13.2); whether any pipeline actually
  gates merges is unknown from the repo.

---

## 18. External references

- Project docs: <https://demsking.gitlab.io/oremi-ohunerin>
- Source / issues: <https://gitlab.com/demsking/oremi-ohunerin>
- Docker Hub: <https://hub.docker.com/r/demsking/oremi-ohunerin>
- YAMNet model: <https://www.kaggle.com/models/google/yamnet/tfLite>
- CMU Sphinx models: <https://sourceforge.net/projects/cmusphinx/files/Acoustic%20and%20Language%20Models/>
- Building a PocketSphinx phonetic dictionary: <https://cmusphinx.github.io/wiki/tutorialdict>
- WebSocket close codes (RFC 6455 §7.4.1): <https://datatracker.ietf.org/doc/html/rfc6455#section-7.4.1>
