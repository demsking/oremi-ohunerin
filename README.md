# Oremi Sound Detection Server

[![pypi version](https://badge.fury.io/py/oremi-sds.svg)](https://pypi.org/project/oremi-sds/)
[![Buy me a beer](https://img.shields.io/badge/Buy%20me-a%20beer-1f425f.svg)](https://www.buymeacoffee.com/demsking)

Oremi Sound Detection Server is a WebSocket server designed to detect sound
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

- [Getting Started with Oremi SDS](#getting-started-with-oremi-sds)
- [Starting the Server with Certificates](#starting-the-server-with-certificates)
- [Oremi Discovery Integration](#oremi-discovery-integration)
- [Oremi Sound Detection Server Protocol](#oremi-sound-detection-server-protocol)
  * [Initialization](#initialization)
  * [Sound Detection](#sound-detection)
  * [Connection Closure Codes](#connection-closure-codes)
  * [Example Implementation](#example-implementation)
- [Contribute](#contribute)
- [Versioning](#versioning)
- [License](#license)

## Getting Started with Oremi SDS

The easiest way to use Oremi SDS is with Docker. Start with Docker for a quick
setup. Follow these steps:

**Using Docker**

Use the official Docker image `demsking/oremi-sds`. Open your terminal and run:

```sh
docker run -d \
  -p 5023:5023 \
  -v ~/.cache/tensorflow/models:/var/oremi/models \
  demsking/oremi-sds
```

This pulls Oremi SDS and starts it on port `5023`. Additionally, the YAMNet
model will be automatically downloaded into the volume named `yamnet.tflite`
for seamless operation.

**Alternative Installation**

If you prefer installing Oremi SDS directly, you'll need to install the
required YAMNet model manualy.

1. Download the install script from the Oremi SDS repository:
   [install-model.sh](https://gitlab.com/demsking/oremi-sds/-/raw/main/scripts/install-model.sh?inline=false)

2. Make the script executable:

   ```bash
   chmod +x install-model.sh
   ```

3. Run the script with the following command:

   ```sh
   # install Yamnet model to "~/.cache/tensorflow/models"
   ./install-model.sh ~/.cache/tensorflow/models/yamnet.tflite
   ```

Now you can install Oremi SDS from PyPi:

```sh
pip install oremi-sds
```

After installation, start Oremi SDS using the provided command.

```sh
usage: oremi-sds [-h] -m MODEL [-t THRESHOLD] [-c CONFIG] [--host HOST] [-p PORT] [--cert-file CERT_FILE] [--key-file KEY_FILE] [--password PASSWORD] [--log-file LOG_FILE] [--verbose] [-v]

Real-time ambient sound and wake word detection

options:
  -h, --help            show this help message and exit
  -m MODEL, --model MODEL
                        Path to the TensorFlow Lite model filename (required).
  -t THRESHOLD, --threshold THRESHOLD
                        Detection threshold for filtering predictions (default: 0.1).
  -c CONFIG, --config CONFIG
                        Path to the configuration file (default: config.json).
  --host HOST           Host address to listen on (default: 127.0.0.1).
  -p PORT, --port PORT  Port number to listen on (default: 5023).
  --cert-file CERT_FILE
                        Path to the certificate file for secure connection.
  --key-file KEY_FILE   Path to the private key file for secure connection.
  --password PASSWORD   Password to unlock the private key (if protected by a password).
  --log-file LOG_FILE   Name of the log file.
  --verbose             Enable verbose logging.
  -v, --version         Show the version of the application.
```

## Starting the Server with Certificates

To start the Oremi SDS server with a certificate, you can use the
`--cert-file` and `--key-file` options to specify the certificate and private
key files. Additionally, if your private key is password-protected, you can use
the `--password` option to provide the password. Here's how to proceed:

1. **Generate a Self-Signed SSL Certificate (For Testing):**

   If you're testing Oremi SDS locally, you can generate a self-signed
   SSL certificate.
   Follow these steps to generate a self-signed certificate using OpenSSL:

   ```sh
   # Generate a self-signed certificate
   openssl req -x509 -nodes -new -sha256 -days 365 -newkey rsa:2048 \
     -subj "/C=CM/CN=localhost" \
     -keyout key.pem \
     -out cert.pem
   ```

   It's important to note that these certificates are self-signed, which means
   they are not issued by a recognized Certificate Authority (CA). While
   suitable for testing and development purposes, self-signed certificates may
   trigger security warnings in browsers and other client applications.

   Please note that this is a simplified example for generating self-signed
   certificates for testing purposes. In production environments, it's
   recommended to obtain SSL certificates from a trusted Certificate
   Authority (CA) like [Let's Encrypt](https://letsencrypt.org/) to ensure
   security and proper authentication..
   Let's Encrypt provides free and automated certificates that are recognized
   by most browsers and clients.

2. **Start the Server using Docker:**

   The quickest way to start the Oremi SDS server with certificates is by
   using Docker. Run the following command in your terminal:

   ```sh
   docker run -d \
      -p 5023:5023 \
      -v ~/.cache/tensorflow/models/yamnet.tflite:/var/oremi/models/yamnet.tflite \
      -v /path/to/cert.pem:/cert.pem \
      -v /path/to/key.pem:/key.pem \
    demsking/oremi-sds \
      --cert-file /cert.pem \
      --key-file /key.pem \
      --password your_private_key_password
   ```

   > Replace `/path/to/cert.pem`, `/path/to/key.pem`, and
   > `your_private_key_password` with the appropriate values.

   This command mounts the certificate and key files into the Docker container
   and starts the server.

## Oremi Discovery Integration

Oremi SDS can work seamlessly with
[Oremi Discovery](https://gitlab.com/demsking/oremi-discovery) to register
itself during startup.

**Oremi Discovery Integration**

Oremi Discovery allows services to register themselves upon startup, making them
discoverable by other components. To integrate Oremi SDS with Oremi Discovery, you can
use the following arguments:

- `--discovery-uri`: Specifies the Oremi SDS URI for connection. For example:
  `--discovery-uri ws://localhost:5105`.

- `--discovery-cert-file` (optional): Specifies the path to the certificate file to use
  for secure connections. If you're using a certificate for secure communication with
  Oremi Discovery, you can provide the certificate using this option. In this case,
  `--discovery-uri` should be `wss://localhost:5105` to indicate a secure WebSocket
  connection.

**Example**

Below is a `docker-compose.yaml` configuration that sets up both Oremi
Discovery and Oremi SDS services with SSL certificates for secure
communication.
The volumes are mounted to read the SSL certificates and models:

```yaml
version: '3.8'
services:
  discovery:
    image: demsking/oremi-discovery
    volumes:
      - ~/.config/oremi/ssl:/etc/ssl:ro
    ports:
      - 5105:5105
    command: [
      "--cert-file", "/etc/ssl/localhost.pem",
      "--key-file", "/etc/ssl/localhost-key.pem",
    ]
  detector:
    image: demsking/oremi-sds
    depends_on:
      - discovery
    volumes:
      - ~/.cache/tensorflow/models/yamnet.tflite:/var/oremi/models/yamnet.tflite:ro
      - ~/.config/oremi/ssl:/etc/ssl:ro
    ports:
      - 5023:5023
    command: [
      "--model", "/var/oremi/models/yamnet.tflite",
      "--cert-file", "/etc/ssl/localhost.pem",
      "--key-file", "/etc/ssl/localhost-key.pem",
      "--discovery-uri", "wss://discovery:5105",
      "--discovery-cert-file", "/etc/ssl/localhost.pem",
    ]
```

In this configuration:

- The `discovery` service runs Oremi Discovery with SSL certificates mounted
  from `~/.config/oremi/ssl`.
- The `stt` service runs Oremi SDS and depends on the `discovery` service. It
  also uses SSL certificates and mounts model from `~/.cache/tensorflow/models`.

For example, you can generate a self-signed certificate using OpenSSL,
specifying the domain name "discovery" as the subject alternative name:

```sh
openssl req -x509 -nodes -new -sha256 -days 365 -newkey rsa:2048 \
  -subj "/C=CM/CN=localhost" \
  -addext "subjectAltName = DNS:discovery" \
  -keyout ~/.config/oremi/ssl/localhost-key.pem \
  -out ~/.config/oremi/ssl/localhost.pem
```

Finally:

```sh
docker-compose up
```

## Oremi Sound Detection Server Protocol

Oremi Sound Detection Server operates using a WebSocket-based protocol for
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
**within 5 seconds** or else the connection will be closed with code `1002`
and reason `Init Timeout`.

```json
{
  "type": "init",
  "language": "fr",
  "features": ["wakeword-detection", "sound-detection"]
}
```

**2. Server**

The server responds with an initialization acknowledgment, providing details
about available languages for wakeword detection:

```json
{
  "type": "init",
  "server": "Oremi Sound Detection Server/1.0.0",
  "status": "ready",
  "languages": ["en", "fr"]
}
```

**Note:** If the client doesn't send the initialization message within **5
seconds**, the server will close the connection with code `1002` and reason
`Init Timeout`.

### Sound Detection

**1. Client**

Once the session is initialized, the client streams audio data in bytes to the
server, with an audio frequency of **16000Hz** and a **single channel**.

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

For an example of how to implement a client for the "Oremi Sound Detection
Server," you can refer to the [client.py file](https://gitlab.com/demsking/oremi-sds/blob/main/client.py)
in the GitLab repository.
The example demonstrates how to connect to the server, send audio data, and
handle the JSON messages received from the server.

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
