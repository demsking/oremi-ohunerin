**Oremi Ohunerin** serves as the real-time audio detection component of the
Oremi Personal Assistant project. It operates as a high-performance WebSocket
server capable of concurrently identifying environmental sounds and detecting
specific wake words to activate the Oremi assistant.

Leveraging cutting-edge technologies like TensorFlow YAMNet for comprehensive
environmental sound classification and PocketSphinx for precise, localized wake
word identification, Ohunerin ensures highly accurate recognition of acoustic
events.

Derived from the Yoruba term _"ohun erin"_, meaning _"sound detection"_, Ohunerin
enables seamless, privacy-first integration of auditory cues into the Oremi
ecosystem, enhancing user experience and interaction.

## Features

- **Real-Time Streaming**: Stream raw PCM audio bytes directly over WebSockets
  for immediate detection results.
- **Ambient Sound Detection**: Classifies environmental sounds (such as shouting,
  laughter, crying, snoring, etc.) using YAMNet.
- **Wake Word Recognition**: Precise wake word detection utilizing PocketSphinx
  with support for multiple languages.
- **Dynamic Session Configuration**: Streamlined selection of features and
  languages per session.
- **Structured Application Settings**: Pydantic Settings integration supporting
  environment variable prefixing (`OREMI_OHUNERIN_`).

## Deployment

### Docker Image

The [`demsking/oremi-ohunerin`](https://hub.docker.com/r/demsking/oremi-ohunerin)
Docker image is officially available on Docker Hub, supporting `linux/amd64`
platform. The image is configured to expose port `5023`, which serves the API
and documentation endpoints.

The local documentation can be accessed at `http://localhost:5023/docs/` for easy
reference on available endpoints and usage instructions.

### Deploy with Docker

Use the official Docker image
[`demsking/oremi-ohunerin`](https://hub.docker.com/r/demsking/oremi-ohunerin) to
run Oremi Ohunerin:

```sh
docker run -d \
  --env-file <path_to_env_file> \
  -p 5023:5023 \
  demsking/oremi-ohunerin
```

Replace `<path_to_env_file>` with the path to your
[environment variables](#environment-variables) file containing the necessary
configurations.

### Deploy with Docker Compose

Create a `compose.yml` file:

```yaml
services:
  ohunerin:
    image: demsking/oremi-ohunerin
    restart: unless-stopped
    ports:
      - 5023:5023
```

Run the container using `docker compose`:

```sh
docker compose up -d
```

### Command Line Interface

#### Installation

Oremi Ohunerin can be installed via `pip`:

```sh
pip install oremi-ohunerin
```

Or using `uv`:

```sh
uv tool install oremi-ohunerin
```

#### Usage

Run the server directly using the `oremi-ohunerin` CLI command:

```sh
oremi-ohunerin [OPTIONS]
```

#### CLI Options

- `-c, --config <path>` – Path to the configuration JSON file.
- `--host <host>` – Host address to listen on (Default: `127.0.0.1`).
- `-p, --port <port>` – Port number to listen on (Default: `5023`).
- `--cert-file <path>` – Path to the SSL certificate file for secure TLS
  connection.
- `--key-file <path>` – Path to the SSL private key file.
- `--password <password>` – Password to unlock the private key.
- `-v, --version` – Show application version and exit.
- `-h, --help` – Show help message and exit.

#### Example Command

```sh
oremi-ohunerin \
  --config /path/to/config.json \
  --host 0.0.0.0 \
  --port 5023
```

## Environment Variables

Environment variables are prefixed with `OREMI_OHUNERIN_`:

### Server

- `OREMI_OHUNERIN_SERVER_HOST` — Host address to listen on (Default: `0.0.0.0`)
- `OREMI_OHUNERIN_SERVER_PORT` — Port number to listen on (Default: `5023`)

### Configuration & Models

- `OREMI_OHUNERIN_CONFIG_PATH` — Path to the JSON configuration file (Default:
  `/oremi/data/config.json`)
- `OREMI_OHUNERIN_MODEL_PATH` — Path to the audio classification model file
  (Default: `/oremi/models/yamnet.tflite`)
- `OREMI_OHUNERIN_THRESHOLD` — Score threshold below which sound detections are
  discarded (Default: `0.1`)

### TLS/SSL

- `OREMI_OHUNERIN_CERT_FILE` — Path to the SSL certificate file
- `OREMI_OHUNERIN_KEY_FILE` — Path to the SSL private key file
- `OREMI_OHUNERIN_PASSWORD` — Password to unlock the SSL private key

### Logging

- `OREMI_OHUNERIN_LOG_LEVEL` — Logging severity level (`DEBUG`, `INFO`, `WARNING`,
  `ERROR`, `CRITICAL`) (Default: `INFO`)
- `OREMI_OHUNERIN_LOG_FILE` — File path for log output (Default: `None` / stderr)

## Configuration File

Ohunerin uses a single unified JSON configuration file: **`config.json`**.

It combines wake word definitions and sound label filtering into one structure.
Default configuration is bundled at `/oremi/config.json`.

### Structure Interface

The structure of the configuration file is defined by the following TypeScript
interfaces:

```typescript
interface OhunerinConfig {
  // List of wakewords and their pronunciations grouped by language.
  wakewords?: WakewordEntry[];

  // Configuration for sound label filtering via allowlist or denylist.
  sounds?: SoundsConfig;
}

interface DictionaryEntry {
  // The word to recognize.
  word: string;
  // One or more phonetic transcriptions for the word.
  phones: string[];
}

interface WakewordEntry {
  // BCP-47 language code (e.g. 'fr', 'en').
  language: string;
  // The wakeword phrase.
  word: string;
  // One or more phonetic transcriptions for the wakeword.
  phones: string[];
  // Optional words that must NOT trigger detection (false-positive guards).
  discriminants?: DictionaryEntry[];
}

interface SoundsConfig {
  // Explicitly enables only the listed sound labels.
  allowlist?: string[];
  // Disables the listed sound labels (used only when allowlist is empty).
  denylist?: string[];
}
```

> [!NOTE]
> Refer to the default [config.json](https://gitlab.com/demsking/oremi-ohunerin/-/blob/main/config.json)
> file in the GitLab repository for a complete example.

### The "sounds" Section

The `"sounds"` object controls which sound labels may be emitted by the sound
detection feature.

If both `allowlist` and `denylist` are empty, all supported sound labels are
enabled.

- **`allowlist`** — Explicitly enables only the listed sound labels. When
  non-empty, `denylist` is ignored.
- **`denylist`** — Disables the listed sound labels. It is used only when
  `allowlist` is empty.

All sound labels must be valid supported labels, and duplicate entries are
removed automatically.

### The "wakewords" Section

The `"wakewords"` list defines the wake words recognized by Ohunerin. It also
stores phonetic pronunciations and optional discriminants used to reduce false
positives.

The `phones` field is especially important. It contains PocketSphinx phoneme
sequences, not IPA notation. Each string is a space-separated list of phonemes
in the pronunciation alphabet expected by PocketSphinx for the selected language
model.

In other words, each entry describes one possible pronunciation of the wake word.

For example, the French wake word `oremi` includes several pronunciation
variants:

- `oo rr ei mm ii`
- `oo rr ai mm ii`
- `au rr ei mm ii`

These variants help the recognizer match different accents, speaking styles, or
small pronunciation differences. The same idea applies to the English entries,
where the phoneme strings use the PocketSphinx English phoneme set, such as
`OW`, `R`, `EH`, `M`, and `IY`.

Discriminants help reduce false positives. For example, if `oremi` could be
confused with `remi`, the discriminant entry provides the pronunciation of
`remi` so the recognizer can better separate the two.

### Editing `config.json`

When editing `config.json`, keep the following in mind:

- Use the phoneme symbols expected by PocketSphinx for the selected language.
- Separate phonemes with spaces.
- Provide multiple `phones` entries when a wake word may be pronounced in more
  than one way.
- Add `discriminants` when a wake word is likely to be confused with another
  word.
- Make sure the pronunciations match the language model being used, since
  phoneme inventories differ between languages.
- Omitting `"sounds"` or `"wakewords"` will cause Ohunerin to use the default
  settings for the omitted section.

### Wake Word Sessions

Wake words are matched by PocketSphinx, whose decoder owns a single native
utterance. Ohunerin therefore checks out one decoder per wake-word session from a
small per-language pool instead of sharing one decoder between clients: sessions
cannot reset or borrow each other's audio, and concurrent clients are detected
independently. The pool holds at most a few decoders per language, and each decoder
costs tens of megabytes of resident memory, so a session that cannot get one is
closed with code `1013` and may be retried once another session ends.

One decoder is kept open across the whole session, so a wake word that straddles a
WebSocket frame boundary is still recognized. Detections are evaluated against the
keyword-spotting threshold `1e-15`; that value was measured on 16 kHz speech and
balances detection in noisy rooms against false positives.

### Connection Closure Codes

| Code   | Meaning                                                                              |
| ------ | ------------------------------------------------------------------------------------ |
| `1000` | Normal closure.                                                                      |
| `1003` | Invalid query parameters, no usable feature requested, or an audio processing error. |
| `1008` | The path is not `/ws`.                                                               |
| `1013` | No wake-word decoder was free; retry once another session ends.                      |
| `4000` | Unexpected error in the socket handler.                                              |

## Contributing

Oremi Ohunerin is built with Python and uses `uv` for dependency management.
The project follows standard Python development practices with type hints,
linting, and automated testing.

For detailed information on setting up your development environment, running
tests, code style guidelines, and the pull request process, please refer to
[CONTRIBUTING.md](https://gitlab.com/demsking/oremi-ohunerin/-/blob/main/CONTRIBUTING.md).

## Versioning

Oremi Ohunerin project adheres to [Semantic Versioning](https://semver.org/)
(SemVer). Version numbers follow the `MAJOR.MINOR.PATCH` format:

- **MAJOR** version increments for incompatible API changes
- **MINOR** version increments for backward-compatible new functionality
- **PATCH** version increments for backward-compatible bug fixes

The current version can be found by running:

```bash
oremi-ohunerin --version
```

## License

Copyright 2023-2026 Sébastien Demanou. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://gitlab.com/demsking/oremi-ohunerin/-/blob/main/LICENSE

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
