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
import logging
import platform

import pydantic
import websockets.exceptions
import websockets.legacy.server

from .detector import DetectorConsumer, DetectorEngine
from .models import Config, DetectedSound, InitMessage, WakewordSetting, create_detected_sound_object
from .trace import Trace
from .vars import APP_DISPLAY_NAME, APP_NAME, ENCODING, __version__
from .wakeword import WakewordEngine

__all__ = [
  'Config',
  'DetectorConsumer',
  'DetectorEngine',
  'DetectedSound',
  'InitMessage',
  'Trace',
  'WakewordEngine',
  'WakewordSetting',
  '__version__',
  'parse_arguments',
  'main',
]


def parse_arguments():
  """Parse command-line arguments.

  Returns:
      argparse.Namespace: The parsed command-line arguments.
  """
  # Create the ArgumentParser instance
  parser = argparse.ArgumentParser(prog=APP_NAME, description=APP_DISPLAY_NAME)

  # Define command-line arguments
  parser.add_argument(
    '-m', '--model',
    type = str,
    required = True,
    help = 'Path to the TensorFlow Lite model filename (required).'
  )

  parser.add_argument(
    '-t', '--threshold',
    type = float,
    default = 0.1,
    help = 'Detection threshold for filtering predictions (default: 0.1).'
  )

  parser.add_argument(
    '-n', '--num-threads',
    type = int,
    default = -1,
    help = 'Number of threads for TensorFlow Lite interpreter (default: -1, auto-select).'
  )

  parser.add_argument(
    '-c', '--config',
    type = str,
    default = 'config.json',
    help = 'Path to the configuration file (default: config.json).'
  )

  parser.add_argument(
    '--host',
    type = str,
    default = '127.0.0.1',
    help = 'Host address to connect to (default: 127.0.0.1).'
  )

  parser.add_argument(
    '-p', '--port',
    type = int,
    default = 5023,
    help = 'Port number to connect to (default: 5023).'
  )

  parser.add_argument(
    '--verbose',
    action = 'store_true',
    help = 'Enable verbose logging.'
  )

  parser.add_argument(
    '-v', '--version',
    action = 'version',
    version = f'%(prog)s {__version__}',
    help = 'Show the version of the application.'
  )

  return parser.parse_args()


async def main():
  args = parse_arguments()
  verbose: bool = args.verbose

  Trace.set_global_level(logging.DEBUG if verbose else logging.INFO)

  logger = Trace.create(__package__)

  logger.info(f'{APP_DISPLAY_NAME} {__version__}')
  logger.info(f'Platform {platform.system()}')
  logger.info(f'Log level {"DEBUG" if logger.level == logging.DEBUG else "INFO"}')
  logger.info(f'Using host {args.host}')
  logger.info(f'Using port {args.port}')
  logger.info(f'Using threshold {args.threshold}')
  logger.info(f'Using model {args.model}')
  logger.info(f'Using config {args.config}')

  config: Config = {}
  server_header = f'{APP_DISPLAY_NAME}/{__version__}'
  detector = DetectorEngine(
    model = args.model,
    score_threshold = args.threshold,
    num_threads = args.num_threads,
    logger = logger,
  )

  with open(args.config, encoding = ENCODING) as file:
    config_content = json.load(file)
    assert isinstance(config_content, dict)
    for language, locale_config in config_content.items():
      logger.info(f'Loading wakeword config for language {language}')
      config[language] = WakewordSetting.model_validate(locale_config)

  async def start(
    websocket: websockets.legacy.server.WebSocketServerProtocol,
    setting: WakewordSetting,
    config: InitMessage,
  ):
    async def send_detected_sound(sound_name: str, score: float):
      sound = create_detected_sound_object(sound_name, score)
      message = json.dumps(sound)
      await websocket.send(message)

    started = False
    wakeword_engine = WakewordEngine(
      setting = setting,
      on_sound_detect = send_detected_sound,
      logger = logger,
    )

    consumer = DetectorConsumer(
      detector,
      num_channels = config.num_channels,
      on_sound_detect = send_detected_sound,
      logger = logger,
    )

    try:
      event = {
        'type': 'init',
        'server': server_header,
      }

      await websocket.send(json.dumps(event))
      logger.info(f'New client: {websocket.request_headers["User-Agent"]}')

      if 'wakeword-detector' in config.features:
        wakeword_engine.start_utt()

      started = True
      async for chunk in websocket:
        if 'wakeword-detector' in config.features:
          wakeword_detected = await wakeword_engine.process_raw(chunk)
          if wakeword_detected:
            consumer.reset_buffer()
            continue
        if 'sound-detector' in config.features:
          await consumer.process_raw(chunk)
    except Exception as error:
      error_message = f'Invalid Message: {error}'
      await websocket.close(code = 1003, reason = error_message)
      logger.error(error_message)
    finally:
      if started and 'wakeword-detector' in config.features:
        wakeword_engine.end_utt()


  async def handler(websocket: websockets.legacy.server.WebSocketServerProtocol):
    loop = asyncio.get_running_loop()
    init_timeout_timer_handler = loop.call_later(5, lambda: loop.create_task(
      websocket.close(code = 1002, reason = 'Init Timeout'),
      name = 'Init Timeout Task',
    ))

    try:
      message = await websocket.recv()
      init_timeout_timer_handler.cancel()
      event = InitMessage.model_validate_json(message)
      wakeword_setting = config[event.language]

      await start(websocket, wakeword_setting, event)
    except (ValueError, pydantic.ValidationError):
      error_message = f'Invalid Init Message: {message}'
      logger.error(error_message)
      await websocket.close(code = 1003, reason = error_message)
    except websockets.exceptions.ConnectionClosedOK as error:
      logger.error(error)
    except Exception as error:
      error_message = f'Unexpected Error: {error}'
      logger.error(error_message)
      await websocket.close(code = 4000, reason = error_message)


  async def listen(host: str, port: int):
    async with websockets.legacy.server.serve(handler, host, port, server_header = server_header, logger = logger):
      await asyncio.Future()  # run forever

  await listen(args.host, args.port)
