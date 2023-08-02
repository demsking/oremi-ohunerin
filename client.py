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
  parser = argparse.ArgumentParser(description="Audio Recorder")

  parser.add_argument(
    "--host",
    type = str,
    default = "localhost",
    help = "Host address to connect to (default: localhost)."
  )

  parser.add_argument(
    "-p", "--port",
    type = int,
    default = 5023,
    help = "Port number to connect to (default: 5023)."
  )

  parser.add_argument(
    "-s", "--sample-rate",
    type = int,
    default = 16000,
    help = "Sample rate for audio recording. Determines the number of audio samples captured per second during recording."
  )

  parser.add_argument(
    "-l", "--chunk-length",
    type = int,
    default = 4000,
    help = "Length of audio chunks for recording. Specifies the number of samples in each audio chunk during recording."
  )

  parser.add_argument(
    "-d", "--device-index",
    type = int,
    default = -1,
    help = "Index of the audio device to be used for recording audio."
  )

  return parser.parse_args()


async def client():
  uri = "ws://localhost:5023"

  audio_queue = asyncio.Queue[bytes]()
  args = parse_arguments()
  stream = sd.RawInputStream(
    dtype = 'int16',
    samplerate = args.sample_rate,
    blocksize = args.chunk_length,
    device = args.device_index if args.device_index > -1 else None,
    callback = lambda indata, frames, time, status: loop.call_soon_threadsafe(audio_queue.put_nowait, bytes(indata)),
  )

  async with websockets.legacy.client.connect(uri, user_agent_header = 'Oremi Sound Detector Client/1.0.0') as websocket:
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, loop.create_task, websocket.close())

    print('Sending init message')
    await websocket.send(json.dumps({
      'type': 'init',
      'num_channels': stream.channels,
      'language': 'fr',
    }))

    init_message_response = await websocket.recv()
    print(init_message_response)

    async def listen():
      print('Listening...')
      async for message in websocket:
        print('>>>', message)

    async def recording():
      print('Recording...')
      with stream:
        while True:
          try:
            data = await audio_queue.get()
            await websocket.send(data)
          except websockets.exceptions.ConnectionClosedError as error:
            print(error)
            break
          except sd.PortAudioError as error:
            print(error)
            break
        print('Stream closed.')

    def handle_listening_task_done(task: asyncio.Task | asyncio.Future):
      if task.exception() is not None:
        print(task)

    def handle_info_task_done(task: asyncio.Task | asyncio.Future):
      if task.exception() is not None:
        print(task)

    listening_task = loop.create_task(listen(), name = 'Listening Task')
    recording_task = loop.create_task(recording(), name = 'Recording Task')

    listening_task.add_done_callback(handle_listening_task_done)
    recording_task.add_done_callback(handle_info_task_done)

    await asyncio.wait([listening_task, recording_task])

try:
  asyncio.run(client())
except KeyboardInterrupt:
  pass
