**Oremi Ohunerin** serves as the real-time audio detection component of the Oremi Personal Assistant project. It operates as a high-performance WebSocket server capable of concurrently identifying environmental sounds and detecting specific wake words to activate the Oremi assistant.

Leveraging cutting-edge technologies like TensorFlow YAMNet for comprehensive environmental sound classification and PocketSphinx for precise, localized wake word identification, Ohunerin ensures highly accurate recognition of acoustic events.

Derived from the Yoruba term _"ohun erin"_, meaning _"sound detection"_, Ohunerin enables seamless, privacy-first integration of auditory cues into the Oremi ecosystem, enhancing user experience and interaction.

## Features

- **Real-Time Streaming**: Stream raw PCM audio bytes directly over WebSockets for immediate detection results.
- **Ambient Sound Detection**: Classifies environmental sounds (such as shouting, laughter, crying, snoring, etc.) using YAMNet.
- **Wake Word Recognition**: Precise wake word detection utilizing PocketSphinx with support for multiple languages.
- **Dynamic Configuration**: Extend wake words and discriminants dynamically per session.
- **Home Assistant Integration**: Standard-compliant integration with Home Assistant's Assist voice pipeline.

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

Ohunerin uses a JSON file (`config.json`) that is validated against the [`OhunerinConfig`](#models/OhunerinConfig) schema. The file defines the detection threshold, wake word entries (one per language/phrase pair), and an optional allowlist of sound labels for the sound-detection feature.

### Schema

| Field         | Type                | Required              | Description                                                       |
|---------------|---------------------|-----------------------|-------------------------------------------------------------------|
| `threshold`   | float               | No (default: 0.65)    | Score below which detections are discarded                        |
| `wakewords`   | WakewordEntry[]     | No                    | Wake word definitions, one per language/phrase pair               |
| `sounds`      | string[]            | No                    | Allowlist of sound labels the sound-detection feature may emit    |

```python
class WakewordEntry:
  """A wakeword definition inside the config file."""

  language: str
  """BCP-47 language code (e.g. 'fr', 'en')."""

  word: str
  """The wakeword phrase."""

  phones: list[str]
  """One or more phonetic transcriptions for the wakeword."""

  discriminants: list[DictionaryEntry] = Field(default_factory=list)
  """Words that must NOT trigger detection (false-positive guards)."""

class DictionaryEntry:
  """A word and its phonetic pronunciations."""

  word: str
  """The word to recognise."""

  phones: list[str]
  """One or more phonetic transcriptions for the word."""
```

### Example `config.json`

```json
{
  "threshold": 0.25,
  "wakewords": [
    {
      "language": "fr",
      "word": "oremi",
      "phones": ["oo rr ei mm ii"],
      "discriminants": [
        { "word": "rémi", "phones": ["rr ei mm ii"] }
      ]
    },
    {
      "language": "fr",
      "word": "dikomlam",
      "phones": [
        "dd ii kk oo mm ll aa mm"
      ]
    },
    {
      "language": "en",
      "word": "oremi",
      "phones": [
        "AO R EY M E"
      ]
    },
    {
      "language": "en",
      "word": "dikomlam",
      "phones": [
        "TH IH K AA M L AA M"
      ]
    }
  ],
  "sounds": [
    "Shout",
    "Laughter",
    "Baby cry, infant cry",
    "Cough",
    "Sneeze"
  ]
}
```

> **Note on acoustic models:** The acoustic model and pronunciation dictionary paths are resolved automatically from conventional locations relative to the config file (`models/wakeword-{lang}/`). They no longer need to be specified in the config file.

## Environment Variables

- **`LOG_LEVEL`**: Logging level. (Default: `"INFO"`)
- **`LOG_FILE`**: Log file path.

## Home Assistant Integration

You can integrate Oremi Ohunerin as a wake word detection engine in Home Assistant's Assist voice pipelines.

### Installation

1. **Download the archive**: Download the latest pre-packaged integration from [here](https://demsking.gitlab.io/oremi-ohunerin/oremi-ohunerin-homeassistant.zip).

2. Extract the archive and copy the `oremi-ohunerin` folder to your Home Assistant configuration directory under `custom_components/oremi_ohunerin` (ensure the target folder uses an underscore, not a hyphen).

   Alternatively, you can copy it manually from the cloned repository:

   ```bash
   cp -r integrations/home-assistant/oremi-ohunerin /path/to/your/homeassistant/config/custom_components/oremi_ohunerin
   ```

3. Restart Home Assistant.

### Configuration

#### Option 1: UI Config Flow (Recommended)

1. Navigate to **Settings** -> **Devices & Services** -> **Integrations**.
2. Click **Add Integration** and search for **Oremi Ohunerin**.
3. Enter the URL of your Oremi Ohunerin server (e.g. `ws://localhost:5023`).
4. Select your default language and submit.

#### Option 2: Manual YAML Configuration

Add the following to your `configuration.yaml` file:

```yaml
wake_word:
  - platform: oremi_ohunerin
    url: 'ws://localhost:5023'
    language: 'fr'
```

- `url` (Required): The WebSocket URL of your running Oremi Ohunerin server.
- `language` (Optional): The default language to use (default: `fr`).
