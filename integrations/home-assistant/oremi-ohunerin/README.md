# Oremi Ohunerin - Home Assistant Integration

This custom component integrates the **Oremi Ohunerin** wake word detection service into Home Assistant, allowing you to use it in your Assist voice pipelines.

## Installation

1. Copy the `oremi-ohunerin` folder to your Home Assistant configuration directory under `custom_components/oremi_ohunerin`.
2. Restart Home Assistant.

## Configuration

### Option 1: UI Config Flow (Recommended)

1. Navigate to **Settings** -> **Devices & Services** -> **Integrations**.
2. Click **Add Integration** and search for **Oremi Ohunerin**.
3. Enter the URL of your Oremi Ohunerin server (e.g. `ws://localhost:5023`).
4. Select your default language.

### Option 2: configuration.yaml

Add the following to your `configuration.yaml` file:

```yaml
wake_word:
  - platform: oremi_ohunerin
    url: "ws://localhost:5023"
    language: "fr"
```

- `url` (Required): The WebSocket URL of your Oremi Ohunerin server.
- `language` (Optional): The default language to use (default: `fr`).
