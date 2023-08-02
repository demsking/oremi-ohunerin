# Oremi Sound Detector Server

[![Buy me a beer](https://img.shields.io/badge/Buy%20me-a%20beer-1f425f.svg)](https://www.buymeacoffee.com/demsking)

Oremi Sound Detector Server is a WebSocket server designed to detect sound
events, including wake words and a predefined list of songs, for the Oremi
Personal Assistant.

The server listens on port `5023` for incoming connections from clients, which
can continuously stream audio data. Once connected, clients can send audio data
in `bytes`, and the server will process it in real-time, detecting sounds and
sending JSON messages back to the client when a sound is recognized.

The program detects the wake word and also a list of sounds including Shout,
Bellows, Children shouting, Laughter, Baby laughter, Crying, sobbing, Baby cry,
infant cry, Whistling, Wheeze, Snoring, Cough, Sneeze, Burping, and Hiccup.

## Install

```sh
pip install oremi_sds
```

## Usage

```sh
usage: oremi-sds [-h] [--host HOST] [-p PORT] -m MODEL [-t THRESHOLD] [-n NUM_THREADS] [-c CONFIG] [--verbose] [-v]

Oremi Sound Detector Server

options:
  -h, --help            show this help message and exit
  --host HOST           Host address to connect to (default: 127.0.0.1).
  -p PORT, --port PORT  Port number to connect to (default: 5023).
  -m MODEL, --model MODEL
                        Path to the TensorFlow Lite model filename (required).
  -t THRESHOLD, --threshold THRESHOLD
                        Detection threshold for filtering predictions (default: 0.2).
  -n NUM_THREADS, --num-threads NUM_THREADS
                        Number of threads for TensorFlow Lite interpreter (default: -1, auto-select).
  -c CONFIG, --config CONFIG
                        Path to the configuration file (default: config.json).
  --verbose             Enable verbose logging.
  -v, --version         Show the version of the application.
```

You can download the model Tensorflow Lite model here:
https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/audio_classification/rpi/lite-model_yamnet_classification_tflite_1.tflite

## Protocol

See [client.py example file](https://gitlab.com/demsking/oremi-sds/blob/main/client.py).

### Initialization

1. When a client connects to the server, it must send an initial JSON
  initiation message with the following structure within 5 seconds or else
  the connection will be closed with code `1002` and reason `Init Timeout`:

  **Init Message Schema**

  ```json
  {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
      "type": {
        "type": "string",
        "enum": ["init"],
        "description": "The type of the message, should be 'init'."
      },
      "num_channels": {
        "type": "integer",
        "description": "The number of audio channels for the audio stream."
      },
      "samplerate": {
        "type": "integer",
        "description": "The sample rate of the audio stream."
      },
      "blocksize": {
        "type": "integer",
        "description": "The block size of audio data sent in each WebSocket message."
      },
      "language": {
        "type": "string",
        "enum": ["fr", "en"],
        "description": "The language used for the detection, should be 'fr' (French) or 'en' (English)."
      },
      "features": {
        "type": "array",
        "items": {
          "type": "string",
          "enum": ["wakeword-detector", "sound-detector"]
        },
        "minItems": 1,
        "description": "The list of features to enable, should include 'wakeword-detector' and/or 'sound-detector'."
      }
    },
    "required": ["type", "num_channels", "samplerate", "blocksize", "language", "features"],
    "description": "JSON Schema for the message structure used during the initialization process."
  }
  ```

2. The server responds with:

  ```json
  {
    "type": "init",
    "server": "Oremi Sound Detector Server/1.0.0"
  }
  ```

**Note:** If the client doesn't send the initialization message within 5
seconds, the server will close the connection with code `1002` and reason
`Init Timeout`.

### Sound Detection

1. Once the session is initialized, the client can continuously send audio
  stream in bytes.

2. The server processes the audio stream in real-time and sends a JSON message
  when it detects a sound with the following structure:

  ```json
  {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
      "type": {
        "type": "string",
        "enum": ["sound"],
        "description": "The type of the message, should be 'sound'."
      },
      "sound": {
        "type": "string",
        "enum": ["wakeword", "shout", "bellows", "children shouting", "laughter", "baby laughter", "crying", "sobbing", "baby cry", "infant cry", "whistling", "wheeze", "snoring", "cough", "sneeze", "burping", "hiccup"],
        "description": "The detected sound type."
      },
      "score": {
        "type": "number",
        "description": "The score indicating the confidence level of the detected sound."
      },
      "datetime": {
        "type": "string",
        "format": "date-time",
        "description": "The timestamp of when the sound was detected."
      }
    },
    "required": ["type", "sound", "score", "datetime"],
    "description": "JSON Schema for the message structure when a sound is detected."
  }
  ```

  **Example for wakeword**

  ```json
  {
    "type": "sound",
    "sound": "wakeword",
    "score": 1.0,
    "datetime": "2023-08-02T20:33:22.805154"
  }
  ```

  **Example for cough**

  ```json
  {
    "type": "sound",
    "sound": "cough",
    "score": 0.4140625,
    "datetime": "2023-08-02T20:41:05.058204"
  }
  ```

### Connection Closure Codes

Possible connection closure codes:

| Code | Reason                                 |
|------|----------------------------------------|
| 1000 | Normal closure                         |
| 1002 | Init Timeout                           |
| 1003 | Invalid Message                        |
| 4000 | Unexpected Error                       |

## License

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License.
You may obtain a copy of the License at [LICENSE](https://gitlab.com/demsking/oremi-sds/blob/main/LICENSE).
