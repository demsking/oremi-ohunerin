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

## Environment Variables

- **`LOG_LEVEL`**: Logging level. (Default: `"INFO"`)
- **`LOG_FILE`**: Log file path.
