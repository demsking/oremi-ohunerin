**Oremi Ohunerin** serves as the real-time audio detection component of the Oremi Personal Assistant project. It operates as a high-performance WebSocket server capable of concurrently identifying environmental sounds and detecting specific wake words to activate the Oremi assistant.

Leveraging cutting-edge technologies like TensorFlow YAMNet for comprehensive environmental sound classification and PocketSphinx for precise, localized wake word identification, Ohunerin ensures highly accurate recognition of acoustic events.

Derived from the Yoruba term _"ohun erin"_, meaning _"sound detection"_, Ohunerin enables seamless, privacy-first integration of auditory cues into the Oremi ecosystem, enhancing user experience and interaction.

---

## Features

- **Real-Time Streaming**: Stream raw PCM audio bytes directly over WebSockets for immediate detection results.
- **Ambient Sound Detection**: Classifies environmental sounds (such as shouting, laughter, crying, snoring, etc.) using YAMNet.
- **Wake Word Recognition**: Precise wake word detection utilizing PocketSphinx with support for multiple languages.
- **Dynamic Configuration**: Extend wake words and discriminants dynamically per session.
- **Home Assistant Integration**: Standard-compliant integration with Home Assistant's Assist voice pipeline.

---

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

---

## Configuration

Ohunerin uses a JSON file (`config.json`) to define pre-configured acoustic models, dictionaries, wake words, and discriminants for each language. This configuration follows the [WakewordSetting](#models/WakewordSetting) schema.

Example `config.json`:

```json
{
  "fr": {
    "model": "models/wakeword-fr/cmusphinx-fr-ptm-8khz-5.2",
    "dictionary": "models/wakeword-fr/pronounciation-dictionary.dict",
    "wakewords": [{ "word": "oremi", "phones": ["oo rr ei mm ii"] }],
    "discriminants": [{ "word": "rémi", "phones": ["rr ei mm ii"] }]
  }
}
```

---

## Environment Variables

- **`THRESHOLD`**: Detection threshold for filtering predictions. (Default: `"0.1"`)
- **`LOG_LEVEL`**: Logging level. (Default: `"INFO"`)
- **`LOG_FILE`**: Log file path.

---

## Home Assistant Integration

You can integrate Oremi Ohunerin as a wake word detection engine in Home Assistant's Assist voice pipelines.

### Installation

1. Copy the `oremi-ohunerin` folder from the `integrations/home-assistant` directory to your Home Assistant configuration directory under `custom_components/oremi_ohunerin`.
2. Restart Home Assistant.

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
