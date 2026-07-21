**Oremi Ohunerin** serves as the real-time audio detection component of the Oremi Personal Assistant project. It operates as a high-performance WebSocket server capable of concurrently identifying environmental sounds and detecting specific wake words to activate the Oremi assistant.

Leveraging cutting-edge technologies like TensorFlow YAMNet for comprehensive environmental sound classification and PocketSphinx for precise, localized wake word identification, Ohunerin ensures highly accurate recognition of acoustic events.

Derived from the Yoruba term _"ohun erin"_, meaning _"sound detection"_, Ohunerin enables seamless, privacy-first integration of auditory cues into the Oremi ecosystem, enhancing user experience and interaction.

## Features

- **Real-Time Streaming**: Stream raw PCM audio bytes directly over WebSockets for immediate detection results.
- **Ambient Sound Detection**: Classifies environmental sounds (such as shouting, laughter, crying, snoring, etc.) using YAMNet.
- **Wake Word Recognition**: Precise wake word detection utilizing PocketSphinx with support for multiple languages.
- **Dynamic Session Configuration**: Streamlined selection of features and languages per session.
- **Structured Application Settings**: Pydantic Settings integration supporting environment variable prefixing (`OREMI_OHUNERIN_`).

## Deployment

### Docker Image

The [`demsking/oremi-ohunerin`](https://hub.docker.com/r/demsking/oremi-ohunerin)
Docker image is officially available on Docker Hub, supporting `linux/amd64`
platform. The image is configured to expose port `5023`, which serves the API
and documentation endpoints.

The local documentation can be accessed at `http://localhost:5023/docs` for easy
reference on available endpoints and usage instructions.

### Deploy with Docker

Use the official Docker image [`demsking/oremi-ohunerin`](https://hub.docker.com/r/demsking/oremi-ohunerin)
to run Oremi Ohunerin:

```sh
docker run -d \
  --env-file <path_to_env_file> \
  -p 5023:5023 \
  demsking/oremi-ohunerin
```

Replace `<path_to_env_file>` with the path to your
[environment variables](#environment-variables) file containing the
necessary configurations.

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

- `-w, --wakewords-config <path>` – Path to the wakewords configuration JSON file.
- `-s, --sounds-config <path>` – Path to the sounds configuration JSON file.
- `--host <host>` – Host address to listen on (Default: `127.0.0.1`).
- `-p, --port <port>` – Port number to listen on (Default: `5023`).
- `--cert-file <path>` – Path to the SSL certificate file for secure TLS connection.
- `--key-file <path>` – Path to the SSL private key file.
- `--password <password>` – Password to unlock the private key.
- `-v, --version` – Show application version and exit.
- `-h, --help` – Show help message and exit.

#### Example Command

```sh
oremi-ohunerin \
  --host 0.0.0.0 \
  --port 5023
```

## Environment Variables

Environment variables are prefixed with `OREMI_OHUNERIN_`:

### Server

- `OREMI_OHUNERIN_SERVER_HOST` — Host address to listen on (Default: `0.0.0.0`)
- `OREMI_OHUNERIN_SERVER_PORT` — Port number to listen on (Default: `5023`)

### TLS/SSL

- `OREMI_OHUNERIN_CERT_FILE` — Path to the SSL certificate file
- `OREMI_OHUNERIN_KEY_FILE` — Path to the SSL private key file
- `OREMI_OHUNERIN_KEY_PASSWORD` — Password to unlock the SSL private key

### Audio Detection

- `OREMI_OHUNERIN_MODEL_PATH` — Path to the audio classification model file
- `OREMI_OHUNERIN_THRESHOLD` — Score threshold below which sound detections are discarded (Default: `0.65`)

### Logging

- `OREMI_OHUNERIN_LOG_LEVEL` — Logging severity level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) (Default: `INFO`)
- `OREMI_OHUNERIN_LOG_FILE` — File path for log output (Default: `None` / stderr)

## Wake Word and Sound Configuration Files

Ohunerin uses two JSON configuration files:

- **`wakeword.json`** defines wake words and their pronunciations.
- **`sounds.json`** configures sound label filtering.

Default versions of both files are bundled with the official Docker image
and the Python wheel distribution.

### Default Locations

When using the Docker image, the files are located at:

- `/oremi/data/wakeword.json`
- `/oremi/data/sounds.json`

### `sounds.json`

The `sounds.json` file controls which sound labels may be emitted by the
sound detection feature.

```json
{
  "allowlist": [],
  "denylist": []
}
```

If both `allowlist` and `denylist` are empty, all supported sound labels
are enabled.

- **`allowlist`** — Explicitly enables only the listed sound labels.
  When non-empty, `denylist` is ignored.
- **`denylist`** — Disables the listed sound labels. It is used only
  when `allowlist` is empty.

All sound labels must be valid supported labels, and duplicate entries
are removed automatically.

### `wakeword.json`

The `wakeword.json` file defines the wake words recognized by Ohunerin.
It also stores phonetic pronunciations and optional discriminants used to
reduce false positives.

Each wake word entry contains:

- **`language`** — The language of the pronunciation model, such as
  `fr` or `en`.
- **`word`** — The wake word as written text.
- **`phones`** — One or more phonetic transcriptions of the wake word.
- **`discriminants`** — Optional alternative words that may sound
  similar and should be distinguished from the wake word.

The `phones` field is especially important. It contains PocketSphinx
phoneme sequences, not IPA notation. Each string is a space-separated
list of phonemes in the pronunciation alphabet expected by PocketSphinx
for the selected language model.

See the for more
details on supported models and pronunciation formats. In other words,
each entry describes one possible pronunciation of the wake word.

For example, the French wake word `oremi` includes several pronunciation
variants:

- `oo rr ei mm ii`
- `oo rr ai mm ii`
- `au rr ei mm ii`

These variants help the recognizer match different accents, speaking
styles, or small pronunciation differences. The same idea applies to the
English entries, where the phoneme strings use the PocketSphinx English
phoneme set, such as `OW`, `R`, `EH`, `M`, and `IY`.

Discriminants help reduce false positives. For example, if `oremi`
could be confused with `remi`, the discriminant entry provides the
pronunciation of `remi` so the recognizer can better separate the two.

```json
[
  {
    "language": "fr",
    "word": "oremi",
    "phones": ["oo rr ei mm ii", "oo rr ai mm ii", "au rr ei mm ii"],
    "discriminants": [
      {
        "word": "remi",
        "phones": ["rr ei mm ii", "rr ai mm ii"]
      }
    ]
  },
  {
    "language": "fr",
    "word": "dikomlam",
    "phones": [
      "dd ii kk oo mm ll aa mm",
      "dd ii kk on ll aa mm",
      "dd ii kk oo mm ll an"
    ]
  },
  {
    "language": "en",
    "word": "oremi",
    "phones": ["OW R EH M IY", "OW R EY M IY", "AO R EH M IY", "AO R EY M IY"],
    "discriminants": [
      {
        "word": "remi",
        "phones": ["R EH M IY", "R EY M IY"]
      }
    ]
  },
  {
    "language": "en",
    "word": "dikomlam",
    "phones": [
      "D IH K AA M L AA M",
      "D IH K AH M L AE M",
      "D IH K AA M L AE M",
      "D IY K AA M L AE M"
    ]
  }
]
```

### Editing `wakeword.json`

When editing `wakeword.json`, keep the following in mind:

- Use the phoneme symbols expected by PocketSphinx for the selected
  language.
- Separate phonemes with spaces.
- Provide multiple `phones` entries when a wake word may be pronounced
  in more than one way.
- Add `discriminants` when a wake word is likely to be confused with
  another word.
- Make sure the pronunciations match the language model being used,
  since phoneme inventories differ between languages.

## Contributing

Oremi Ohunerin is built with Python and uses `uv` for dependency management. The
project follows standard Python development practices with type hints, linting,
and automated testing.

For detailed information on setting up your development environment, running
tests, code style guidelines, and the pull request process, please refer to
[CONTRIBUTING.md](https://gitlab.com/demsking/oremi-ohunerin/-/blob/main/CONTRIBUTING.md).

## Versioning

Oremi Ohunerin follows [Semantic Versioning](https://semver.org/). Display the
installed version with:

```bash
oremi-ohunerin --version
```

## License

Copyright 2023-2026 Sébastien Demanou. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
