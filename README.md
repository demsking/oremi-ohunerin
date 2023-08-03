# Oremi Sound Detector Server

[![Buy me a beer](https://img.shields.io/badge/Buy%20me-a%20beer-1f425f.svg)](https://www.buymeacoffee.com/demsking)

Oremi Sound Detector Server is a WebSocket server designed to detect sound
events, including wake words and a predefined list of songs, for the Oremi
Personal Assistant.

The server listens on port `5023` for incoming connections from clients, which
can continuously stream audio data. Once connected, clients can send audio
data in `bytes`, and the server will process it in real-time, detecting sounds
and sending JSON messages back to the client when a sound is recognized.

Oremi SDS detects the Oremi wake word including sounds: Shout, Bellows,
Children shouting, Laughter, Baby laughter, Crying, sobbing, Baby cry, infant
cry, Whistling, Wheeze, Snoring, Cough, Sneeze, Burping, and Hiccup.

## Table of Contents

- [Install](#install)
- [Usage](#usage)
- [Protocol](#protocol)
  * [Initialization](#initialization)
  * [Sound Detection](#sound-detection)
  * [Connection Closure Codes](#connection-closure-codes)
  * [Example Implementation](#example-implementation)
- [Contribute](#contribute)
- [Versioning](#versioning)
- [License](#license)

## Install

```sh
pip install Oremi-SDS
```

## Usage

```sh
usage: oremi-sds [-h] [--host HOST] [-p PORT] -m MODEL [-t THRESHOLD] [-n NUM_THREADS] [-c CONFIG] [--verbose] [-v]

Oremi Sound Detector Server

options:
  -h, --help            show this help message and exit
  -m MODEL, --model MODEL
                        Path to the TensorFlow Lite model filename (required).
  -t THRESHOLD, --threshold THRESHOLD
                        Detection threshold for filtering predictions (default: 0.1).
  -n NUM_THREADS, --num-threads NUM_THREADS
                        Number of threads for TensorFlow Lite interpreter (default: -1, auto-select).
  -c CONFIG, --config CONFIG
                        Path to the configuration file (default: config.json).
  --host HOST           Host address to connect to (default: 127.0.0.1).
  -p PORT, --port PORT  Port number to connect to (default: 5023).
  --verbose             Enable verbose logging.
  -v, --version         Show the version of the application.
```

You can download the model Tensorflow Lite model here:
https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/audio_classification/rpi/lite-model_yamnet_classification_tflite_1.tflite

## Protocol

Oremi Sound Detector Server operates using a WebSocket-based protocol for
real-time sound detection. The protocol involves an initialization step where
the client provides essential details such as the number of audio channels,
sample rate, block size, language, and features to enable. Once the session is
initialized, the client can continuously stream audio data to the server. The
server processes the audio in real-time and sends JSON messages back to the
client when it detects specific sounds, such as wake words or predefined
songs.

The section outlines the message structures, initialization process, sound
detection mechanism, and possible connection closure codes. Developers can use
this protocol documentation as a reference to interact with the server and
build their applications accordingly.

### Initialization

**1. Client**

When a client connects to the server, it must send an initial
[JSON initiation message](https://gitlab.com/demsking/oremi-sds/blob/main/schemas/InitMessage.json)
within 5 seconds or else the connection will be closed with code `1002` and
reason `Init Timeout`.

```json
{
  "type": "init",
  "language": "fr",
  "samplerate": 16000,
  "num_channel": 1,
  "blocksize": 4000,
  "features": ["wakeword-detector", "sound-detector"]
}
```

**2. Server**

The server responds with:

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

**1. Client**

Once the session is initialized, the client can continuously send audio
stream in bytes.

**2. Server**

The server processes the audio stream in real-time and sends a
[JSON sound message](https://gitlab.com/demsking/oremi-sds/blob/main/schemas/DetectedSoundSchema.json)
when it detects a sound:

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

- `1000`: Indicates a normal closure, meaning that the purpose for which the connection was established has been fulfilled.
- `1002`: Init Timeout
- `1003`: Invalid Message
- `4000`: Unexpected Error

### Example Implementation

For an example of how to implement a client for the "Oremi Sound Detector
Server," you can refer to the [client.py file](https://gitlab.com/demsking/oremi-sds/blob/main/client.py)
in the GitLab repository.
The example demonstrates how to connect to the
server, send audio data, and handle the JSON messages received from the
server.

## Contribute

Please follow [CONTRIBUTING.md](https://gitlab.com/demsking/oremi-sds/blob/main/CONTRIBUTING.md).

## Versioning

Given a version number `MAJOR.MINOR.PATCH`, increment the:

- `MAJOR` version when you make incompatible API changes,
- `MINOR` version when you add functionality in a backwards-compatible manner,
  and
- `PATCH` version when you make backwards-compatible bug fixes.

Additional labels for pre-release and build metadata are available as extensions
to the `MAJOR.MINOR.PATCH` format.

See [SemVer.org](https://semver.org/) for more details.

## License

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License.
You may obtain a copy of the License at [LICENSE](https://gitlab.com/demsking/oremi-sds/blob/main/LICENSE).
