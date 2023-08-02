# Copyright 2023 Sébastien Demanou. All Rights Reserved.
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
import signal

import sounddevice as sd
import websockets.exceptions
import websockets.legacy.client


def parse_arguments():
  """Parse command-line arguments.

  Returns:
      argparse.Namespace: The parsed command-line arguments.
  """
  parser = argparse.ArgumentParser(description='Audio Recorder')

  parser.add_argument(
    '--host',
    type = str,
    default = 'localhost',
    help = 'Host address to connect to (default: localhost).'
  )

  parser.add_argument(
    '-p', '--port',
    type = int,
    default = 5023,
    help = 'Port number to connect to (default: 5023).'
  )

  parser.add_argument(
    '-s', '--sample-rate',
    type = int,
    default = 16000,
    help = 'Sample rate for audio recording. Determines the number of audio samples captured per second during recording.'
  )

  parser.add_argument(
    '-b', '--block-size',
    type = int,
    default = 4000,
    help = 'Length of audio chunks for recording. Specifies the number of samples in each audio chunk during recording.'
  )

  parser.add_argument(
    '-d', '--device-index',
    type = int,
    default = -1,
    help = 'Index of the audio device to be used for recording audio.'
  )

  return parser.parse_args()


async def client():
  uri = 'ws://localhost:5023'

  audio_queue = asyncio.Queue[bytes]()
  args = parse_arguments()
  stream = sd.RawInputStream(
    dtype = 'int16',
    samplerate = args.sample_rate,
    blocksize = args.block_size,
    device = args.device_index if args.device_index > -1 else None,
    callback = lambda indata, frames, time, status: loop.call_soon_threadsafe(audio_queue.put_nowait, bytes(indata)),
  )

  async with websockets.legacy.client.connect(uri, user_agent_header = 'Oremi Sound Detector Client/1.0.0') as websocket:
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, lambda: loop.create_task(websocket.close(), name = 'SIGINT Signal Task'))
    loop.add_signal_handler(signal.SIGTERM, lambda: loop.create_task(websocket.close(), name = 'SIGTERM Signal Task'))

    print('Sending init message')
    await websocket.send(json.dumps({
      'type': 'init',
      'language': 'fr',
      'num_channels': stream.channels,
      'samplerate': args.sample_rate,
      'blocksize': args.block_size,
    }))

    init_message_response = await websocket.recv()
    print(init_message_response)

    async def listen():
      print('Listening...')
      try:
        async for message in websocket:
          print('>>>', message)
      except asyncio.CancelledError:
        print('Recording cancelled')
      finally:
        await websocket.close()

    async def recording():
      print('Recording...')
      with stream:
        while True:
          try:
            data = await audio_queue.get()
            await websocket.send(data)
          except websockets.exceptions.ConnectionClosedOK:
            print('Connection closed')
            break
          except websockets.exceptions.ConnectionClosedError as error:
            print(error)
            break
          except sd.PortAudioError as error:
            print(error)
            break
      print('Stream closed.')

    def handle_task_done(task: asyncio.Task):
      if task.done():
        print(f'{task.get_name()} done')
      elif task.cancelled():
        print(f'{task.get_name()} cancelled')
      else:
        try:
          if task.exception() is not None:
            print(task)
        except (asyncio.CancelledError, asyncio.InvalidStateError) as error:
          print(error)

    listening_task = loop.create_task(listen(), name = 'Listening Task')
    recording_task = loop.create_task(recording(), name = 'Recording Task')

    listening_task.add_done_callback(handle_task_done)
    recording_task.add_done_callback(handle_task_done)

    await asyncio.wait([listening_task, recording_task])


asyncio.run(client())
