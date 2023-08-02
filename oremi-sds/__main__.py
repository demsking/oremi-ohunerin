import argparse
import asyncio
import json
import logging
import platform
import secrets

import websockets.exceptions
import websockets.legacy.server

from .detector import DetectorConsumer, DetectorEngine
from .models import Config, WakewordSetting
from .trace import Trace
from .vars import APP_DISPLAY_NAME, APP_NAME, ENCODING, __version__
from .wakeword import WakewordEngine


def parse_arguments():
  """Parse command-line arguments.

  Returns:
      argparse.Namespace: The parsed command-line arguments.
  """
  # Create the ArgumentParser instance
  parser = argparse.ArgumentParser(prog=APP_NAME, description=APP_DISPLAY_NAME)

  # Define command-line arguments
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
    '-m', '--model',
    type = str,
    required = True,
    help = 'Path to the TensorFlow Lite model filename (required).'
  )

  parser.add_argument(
    '-t', '--threshold',
    type=float,
    default = 0.2,
    help = 'Detection threshold for filtering predictions (default: 0.2).'
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
    '--verbose',
    action='store_true',
    help = 'Enable verbose logging.'
  )

  parser.add_argument(
    '-v', '--version',
    action='version',
    version=f'%(prog)s {__version__}',
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
    ws: websockets.legacy.server.WebSocketServerProtocol,
    setting: WakewordSetting,
    num_channels: int,
  ):
    wakeword_engine = WakewordEngine(setting, logger)
    consumer = DetectorConsumer(
      detector,
      num_channels = num_channels,
      wakeword_engine = wakeword_engine,
      on_sound_detect = lambda sound: ws.send(json.dumps(sound)),
      logger = logger,
    )

    try:
      event = {
        "type": "init",
        "server": server_header,
      }

      await ws.send(json.dumps(event))
      logger.info(f'New client: {ws.request_headers["User-Agent"]}')

      consumer.start_utt()
      async for message in ws:
        await consumer.process_raw(message)
    except Exception as error:
      error_message = f'Invalid message: {error}'
      await ws.close(code = 1003, reason = error_message)
      logger.error(error_message)
    finally:
      consumer.end_utt()


  async def handler(ws: websockets.legacy.server.WebSocketServerProtocol):
    loop = asyncio.get_running_loop()
    init_timeout_timer_handler = loop.call_later(
      5,
      lambda: loop.create_task(ws.close(code = 1002, reason = 'Init Timeout'), name = 'Init Timeout Task'),
    )

    try:
      message = await ws.recv()
      init_timeout_timer_handler.cancel()
      event = json.loads(message)

      assert event["type"] == "init", f"Invalid init message: {event}"
      assert isinstance(event["num_channels"], int), "Missing mandatory 'num_channels' field"
      assert isinstance(event["language"], str), "Missing mandatory 'language' field"
      assert event["language"] in config, f"Unsupported language '{event['language']}'"

      language = event["language"]
      wakeword_setting = config[language]

      await start(ws, wakeword_setting, event['num_channels'])
    except websockets.exceptions.ConnectionClosedOK as error:
      logger.error(error)
    except AssertionError as error:
      logger.error(error)
      await ws.close(code = 1002, reason = str(error))
    except Exception as error:
      error_message = f'Unexpected error: {error}'
      logger.error(error_message)
      await ws.close(code = 4000, reason = error_message)


  async def listen(host: str, port: int):
    async with websockets.legacy.server.serve(handler, host, port, server_header = server_header, logger = logger):
      await asyncio.Future()  # run forever

  await listen(args.host, args.port)


try:
  asyncio.run(main())
except KeyboardInterrupt:
  pass
