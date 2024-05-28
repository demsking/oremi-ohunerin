# Oremi Ohunerin

[![pypi version](https://badge.fury.io/py/oremi-ohunerin.svg)](https://pypi.org/project/oremi-ohunerin/)
[![Buy me a beer](https://img.shields.io/badge/Buy%20me-a%20beer-1f425f.svg)](https://www.buymeacoffee.com/demsking)

Oremi Ohunerin is the real-time audio detection component of the Oremi Personal
Assistant project, operating as a websocket server proficient in identifying
environmental sounds and the specific wake word to activate Oremi.

Leveraging cutting-edge technologies such as Tensorflow YAMNet for comprehensive
audio detection and PocketSphinx for precise wake word identification, this
component ensures accurate recognition of various sound categories, including
but not limited to shouts, laughter, crying, and more.

Derived from the Yoruba term "ohun erin," meaning "sound detection," Ohunerin
embodies the essence of its function, facilitating seamless integration of
auditory cues into the Oremi ecosystem, thus enhancing user experience and
interaction.

## Table of Contents

- [Getting Started with Oremi Ohunerin](#getting-started-with-oremi-ohunerin)
- [Environment Variables](#environment-variables)
- [Starting Ohunerin with Certificates](#starting-ohunerin-with-certificates)
- [Oremi Ohunerin Protocol](#oremi-ohunerin-protocol)
  * [Initialization](#initialization)
  * [Sound Detection](#sound-detection)
  * [Connection Closure Codes](#connection-closure-codes)
  * [Example Implementation](#example-implementation)
- [Contribute](#contribute)
- [Versioning](#versioning)
- [License](#license)

## Getting Started with Oremi Ohunerin

The easiest way to use Oremi Ohunerin is with Docker. Start with Docker for a
quick setup. Follow these steps:

**Using Docker**

Use the official Docker image [`demsking/oremi-ohunerin`](https://hub.docker.com/r/demsking/oremi-ohunerin)
to run Oremi Ohunerin:

```sh
docker run -d \
  --env-file <path_to_env_file> \
  -p 5023:5023 \
  -v ~/.cache/tensorflow/models:/var/oremi/models \
  demsking/oremi-ohunerin
```

Replace `<path_to_env_file>` with the path to your environment variable file
containing the necessary configurations.

This pulls Oremi Ohunerin and starts it on port `5023`. Additionally, the YAMNet
model will be automatically downloaded into the volume named `yamnet.tflite`
for seamless operation.

**Alternative Installation**

If you prefer installing Oremi Ohunerin directly, you'll need to install the
required YAMNet model manualy.

1. Download the install script from the Oremi Ohunerin repository:
   [install-model.sh](https://gitlab.com/demsking/oremi-ohunerin/-/raw/main/scripts/install-model.sh?inline=false)

2. Make the script executable:

   ```bash
   chmod +x install-model.sh
   ```

3. Run the script with the following command:

   ```sh
   # install Yamnet model to "~/.cache/tensorflow/models"
   ./install-model.sh ~/.cache/tensorflow/models/yamnet.tflite
   ```

Now you can install Oremi Ohunerin from PyPi:

```sh
pip install oremi-ohunerin
```

After installation, start Oremi Ohunerin using the provided command.

```sh
usage: oremi-ohunerin [-h] -m MODEL [-t THRESHOLD] [-c CONFIG] [--host HOST] [-p PORT] [--cert-file CERT_FILE] [--key-file KEY_FILE] [--password PASSWORD] [-v]

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
  -v, --version         Show the version of the application.
```

## Environment Variables

The following environment variables can be used to configure the Oremi Ohunerin
Docker containers:

| Variable        | Description                     | Default Value |
|-----------------|---------------------------------|---------------|
| **Logging**                                                       |
| LOG_LEVEL       | Logging level                   | "info"        |
| LOG_FILE        | Log file path                   |               |
| **Discovery**                                                     |
| DISCOVERY_URL   | Discovery channel configuration |               |
| SERVICE_URI     | Discovery service URI           |               |

## Starting Ohunerin with Certificates

To start the Oremi Ohunerin with a certificate, you can use the `--cert-file`
and `--key-file` options to specify the certificate and private key files.
Additionally, if your private key is password-protected, you can use the
`--password` option to provide the password. Here's how to proceed:

1. **Generate a Self-Signed SSL Certificate (For Testing):**

   If you're testing Oremi Ohunerin locally, you can generate a self-signed
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

2. **Start Ohunerin using Docker:**

   The quickest way to start the Oremi Ohunerin server with certificates is by
   using Docker. Run the following command in your terminal:

   ```sh
   docker run -d \
      -p 5023:5023 \
      -v ~/.cache/tensorflow/models/yamnet.tflite:/var/oremi/models/yamnet.tflite \
      -v /path/to/cert.pem:/cert.pem \
      -v /path/to/key.pem:/key.pem \
    demsking/oremi-ohunerin \
      --cert-file /cert.pem \
      --key-file /key.pem \
      --password your_private_key_password
   ```

   > Replace `/path/to/cert.pem`, `/path/to/key.pem`, and
   > `your_private_key_password` with the appropriate values.

   This command mounts the certificate and key files into the Docker container
   and starts the server.

## Oremi Ohunerin Protocol

Oremi Ohunerin websocket server listens on port `5023` for incoming connections
from clients, which can continuously stream audio data. Once connected, clients
can send audio data in `bytes`, and the server will process it in real-time,
detecting sounds and sending JSON messages back to the client when a sound is
recognized.

The protocol involves an initialization step where the client provides essential
details such as the number of audio channels, sample rate, block size, language,
and features to enable. Once the session is initialized, the client can
continuously stream audio data to the server. The server processes the audio in
real-time and sends JSON messages back to the client when it detects specific
sounds, such as wake words or predefined songs.

The section outlines the message structures, initialization process, sound
detection mechanism, and possible connection closure codes. Developers can use
this protocol documentation as a reference to interact with the server and
build their applications accordingly.

### Initialization

**1. Client**

When a client connects to the server, it must send an initial
[JSON initiation message](https://gitlab.com/demsking/oremi-ohunerin/blob/main/schemas/InitMessage.json)
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
  "server": "oremi-ohunerin/1.0.0",
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
[JSON sound message](https://gitlab.com/demsking/oremi-ohunerin/blob/main/schemas/DetectedSoundSchema.json)
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

For an example of how to implement a client for the "Oremi Ohunerin", you can
refer to the [client.py file](https://gitlab.com/demsking/oremi-ohunerin/blob/main/client.py)
in the GitLab repository.
The example demonstrates how to connect to the server, send audio data, and
handle the JSON messages received from the server.

## Contribute

Please follow [CONTRIBUTING.md](https://gitlab.com/demsking/oremi-ohunerin/blob/main/CONTRIBUTING.md).

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
You may obtain a copy of the License at [LICENSE](https://gitlab.com/demsking/oremi-ohunerin/blob/main/LICENSE).
