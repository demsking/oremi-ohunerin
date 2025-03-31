# Copyright 2023-2025 Sébastien Demanou. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
import argparse
import asyncio
import json
import logging
import signal
import ssl

import sounddevice as sd
import websockets.exceptions
from oremi_core.logger import Logger
from websockets.asyncio.client import connect


def parse_arguments() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description='Oremi SDS Client')

  parser.add_argument(
    '-l',
    '--language',
    type=str,
    default='fr',
  )

  parser.add_argument(
    '-i',
    '--device-index',
    type=int,
    default=-1,
    help='Index of the audio device to be used for recording audio.',
  )

  parser.add_argument(
    '-d',
    '--device',
    type=str,
    default='',
    help='Name of the device.',
  )

  parser.add_argument(
    '--list-devices',
    action='store_true',
    help='List available input devices.',
  )

  parser.add_argument(
    '--host',
    type=str,
    default='localhost',
    help='Host address to connect to (default: localhost).',
  )

  parser.add_argument(
    '-p',
    '--port',
    type=int,
    default=5023,
    help='Port number to connect to (default: 5023).',
  )

  parser.add_argument(
    '--cert-file',
    type=str,
    help='Path to the certificate file for secure connection.',
  )

  return parser.parse_args()


def list_input_devices():
  devices = sd.query_devices()
  print('Available input devices:')
  for i, device in enumerate(devices):
    if device['max_input_channels'] > 0:  # type: ignore
      print(
        f"{i + 1}. {device['name']} - {device['max_input_channels']} channel(s) - Sample rate: {device['default_samplerate']} Hz"  # type: ignore
      )


async def main():
  audio_queue = asyncio.Queue[bytes]()
  args = parse_arguments()

  if args.list_devices:
    list_input_devices()
    return

  uri = f"wss://{args.host}:{args.port}" if args.cert_file else f"ws://{args.host}:{args.port}"
  stream = sd.RawInputStream(
    dtype='int16',
    samplerate=16000,
    blocksize=4000,
    device=args.device or (args.device_index - 1 if args.device_index > 0 else None),
    channels=1,
    callback=lambda indata, frames, time, status: loop.call_soon_threadsafe(audio_queue.put_nowait, bytes(indata)),
  )

  device_info = sd.query_devices(stream.device, 'input')
  logger = Logger.create('sds-client', level=logging.DEBUG)
  stream_open = True
  ssl_context = None

  if args.cert_file:
    logger.info(f'Using certificat file "{args.cert_file}"')
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.load_verify_locations(args.cert_file)

  def stop_recording():
    print('Ctrl+C received, closing stream...')
    if stream_open:
      stream.stop()
      stream.close()
      print('Stream closed.')

  async with connect(uri, ssl=ssl_context, user_agent_header='sds-client/1.0.0') as websocket:
    loop = asyncio.get_running_loop()

    loop.add_signal_handler(signal.SIGINT, stop_recording)
    loop.add_signal_handler(signal.SIGTERM, stop_recording)
    loop.add_signal_handler(signal.SIGINT, lambda: loop.create_task(websocket.close(), name='SIGINT Signal Task'))
    loop.add_signal_handler(signal.SIGTERM, lambda: loop.create_task(websocket.close(), name='SIGTERM Signal Task'))

    logger.info('Waiting server init message')
    server_init_message = await websocket.recv()
    logger.info(server_init_message)

    logger.info('Sending init message')
    await websocket.send(
      json.dumps(
        {
          'type': 'init',
          'features': [
            {
              'name': 'wakeword-detection',
              'language': args.language,
              'wakewords': [
                {'word': 'alexa', 'phones': ['aa ll ei kk ss aa']},
                {'word': 'ok google', 'phones': ['oh k eh g uw g ah l']},
              ],
              'discriminants': [{'word': 'alex', 'phones': ['aa ll ai kk ss']}, {'word': 'google', 'phones': ['g uw g ah l']}],
            },
            {
              'name': 'sound-detection',
              'allowlist': [
                'Shout',  # Cri
                'Bellows',  # Sonner
                'Children shouting',  # Cris d'enfants
                'Laughter',  # Rire
                'Baby laughter',  # Rire de bébé
                'Crying, sobbing',  # Pleurer, sangloter
                'Baby cry, infant cry',  # Cri de bébé, pleurs d'enfant
                'Whistling',  # Siffler
                'Wheeze',  # Wheeze
                'Snoring',  # Ronfler
                'Cough',  # Tousserq
                'Sneeze',  # Éternuer
                'Burping',  # Roter
                'Hiccup',  # Hoqueter
              ],
            },
          ],
        },
      )
    )

    logger.info('Waiting server ready message')
    server_ready_message = await websocket.recv()
    logger.info(server_ready_message)

    async def listen():
      logger.info('Listening detection messages...')
      try:
        async for message in websocket:
          logger.info(
            f"Detected: {message}"
          )  # {"type": "sound", "sound": "snoring", "score": 0.109375, "datetime": "2023-08-16T14:42:46.424809"}
      except asyncio.CancelledError:
        logger.info('Recording stopped')
        await websocket.close()
      except websockets.exceptions.ConnectionClosedOK:
        logger.info('Connection closed')
      except websockets.exceptions.ConnectionClosedError as error:
        logger.info(error)

    async def recording():
      logger.info(f"Recording from {device_info['name']} device...")  # type: ignore
      with stream:
        while stream_open:
          try:
            data = await audio_queue.get()
            await websocket.send(data)
          except websockets.exceptions.ConnectionClosedOK:
            logger.info('Connection closed')
            break
          except websockets.exceptions.ConnectionClosedError as error:
            logger.info(error)
            break
          except sd.PortAudioError as error:
            logger.info(error)
            break
      logger.info('Stream closed.')

    def handle_task_done(task: asyncio.Task):
      if task.done():
        logger.info(f"{task.get_name()} done")
      elif task.cancelled():
        logger.info(f"{task.get_name()} cancelled")
      else:
        try:
          if task.exception() is not None:
            logger.info(task)
        except (asyncio.CancelledError, asyncio.InvalidStateError) as error:
          logger.info(error)

    listening_task = loop.create_task(listen(), name='Listening Task')
    recording_task = loop.create_task(recording(), name='Recording Task')

    listening_task.add_done_callback(handle_task_done)
    recording_task.add_done_callback(handle_task_done)

    await asyncio.wait([listening_task, recording_task])


try:
  asyncio.run(main())
except KeyboardInterrupt:
  pass
