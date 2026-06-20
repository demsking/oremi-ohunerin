**Oremi Ohunerin** serves as the real-time audio detection component of the Oremi Personal Assistant project. It operates as a high-performance WebSocket server capable of concurrently identifying environmental sounds and detecting specific wake words to activate the Oremi assistant.

Leveraging cutting-edge technologies like TensorFlow YAMNet for comprehensive environmental sound classification and PocketSphinx for precise, localized wake word identification, Ohunerin ensures highly accurate recognition of acoustic events.

Derived from the Yoruba term _"ohun erin"_, meaning _"sound detection"_, Ohunerin enables seamless, privacy-first integration of auditory cues into the Oremi ecosystem, enhancing user experience and interaction.

## Features

- **Real-Time Streaming**: Stream raw PCM audio bytes directly over WebSockets for immediate detection results.
- **Ambient Sound Detection**: Classifies environmental sounds (such as shouting, laughter, crying, snoring, etc.) using YAMNet.
- **Wake Word Recognition**: Precise wake word detection utilizing PocketSphinx with support for multiple languages.
- **Dynamic Configuration**: Extend wake words and discriminants dynamically per session.

## Deployment

### Docker Setup

Use the official Docker image [`demsking/oremi-ohunerin`](https://hub.docker.com/r/demsking/oremi-ohunerin) to run Oremi Ohunerin:

```sh
docker run -d -p 5023:5023 demsking/oremi-ohunerin
```

To run the container with a custom configuration file (`config.json`), mount the file inside the container and pass it via the `--config` option:

```sh
docker run -d \
  -p 5023:5023 \
  -v /path/to/custom/config.json:/var/oremi/config.json:ro \
  demsking/oremi-ohunerin --config /var/oremi/config.json
```

Once deployed, the documentation site can be accessed at `http://localhost:5023/docs`.

### Alternative Installation

If you prefer installing Oremi Ohunerin directly:

1. Install the package from PyPI:

   ```sh
   pip install oremi-ohunerin
   ```

2. Start the server:
   ```sh
   oremi-ohunerin
   ```

## Configuration

Ohunerin uses a JSON file (`config.json`) that is validated against the [`OhunerinConfig`](#models/OhunerinConfig) schema.
The file defines the detection threshold, wake word entries (one per language/phrase pair), and an optional allowlist of sound labels for the sound-detection feature.

**Example `config.json`**

```json
{
  "threshold": 0.25,
  "wakewords": [
    {
      "language": "fr",
      "word": "oremi",
      "phones": ["oo rr ei mm ii"],
      "discriminants": [{ "word": "rémi", "phones": ["rr ei mm ii"] }]
    },
    {
      "language": "fr",
      "word": "dikomlam",
      "phones": ["dd ii kk oo mm ll aa mm"]
    },
    {
      "language": "en",
      "word": "oremi",
      "phones": ["AO R EY M E"]
    },
    {
      "language": "en",
      "word": "dikomlam",
      "phones": ["TH IH K AA M L AA M"]
    }
  ],
  "sounds": ["Shout", "Laughter", "Baby cry, infant cry", "Cough", "Sneeze"]
}
```

## Logging

Logging is configured only through environment variables:

**Environment Variables:**

- `LOG_LEVEL` – Logging severity level. One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. Invalid values fall back to `INFO`. Default: `INFO`
- `LOG_FILE` – File path for log output. Must be writable by the process. Default: Standard error (stderr)

**Example:**

```bash
LOG_LEVEL=DEBUG LOG_FILE=/var/log/oremi-ohunerin.log oremi-ohunerin
```

**Docker example:**

```bash
docker run --rm -it \
  -e LOG_LEVEL=DEBUG \
  -e LOG_FILE=/var/log/oremi-ohunerin.log \
  -v /var/log:/var/log \
  demsking/oremi-ohunerin
```

**Notes:**

- Setting `LOG_LEVEL=DEBUG` provides verbose output useful for troubleshooting
- When using Docker, ensure the log directory is mounted with `-v` to persist logs outside the container
- If `LOG_FILE` points to a directory that doesn't exist, the process will fail to start

## Development

Oremi Device is built with Python and uses `uv` for dependency management. The project follows standard Python development practices with type hints, linting, and automated testing.

For detailed information on setting up your development environment, running tests, code style guidelines, and the pull request process, please refer to [CONTRIBUTING.md](https://gitlab.com/demsking/oremi-ohunerin/-/blob/main/CONTRIBUTING.md).

## Versioning

This project adheres to [Semantic Versioning](https://semver.org/) (SemVer). Version numbers follow the `MAJOR.MINOR.PATCH` format:

- **MAJOR** version increments for incompatible API changes
- **MINOR** version increments for backward-compatible new functionality
- **PATCH** version increments for backward-compatible bug fixes

The current version can be found in `pyproject.toml` or by running:

```bash
oremi-ohunerin --version
```

Pre-release versions (alpha, beta, release candidates) may be published to PyPI for testing purposes and are clearly marked with version suffixes.

## License

Copyright 2026 Sébastien Demanou. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
