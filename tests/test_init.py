# Copyright 2026 Sébastien Demanou. All Rights Reserved.
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
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from ohunerin import main
from ohunerin import start


@pytest.mark.asyncio
async def test_start():
  mock_args = MagicMock()
  mock_args.config = None
  mock_args.threshold = 0.15
  mock_args.host = "127.0.0.1"
  mock_args.port = 5023
  mock_args.cert_file = None
  mock_args.key_file = None
  mock_args.password = None

  async def dummy_listen(host, port):
    pass

  mock_server = MagicMock()
  mock_server.listen = MagicMock(side_effect=dummy_listen)
  mock_server.data_path = "/mock/model.tflite"

  mock_settings = MagicMock()
  mock_settings.server_host = "127.0.0.1"
  mock_settings.server_port = 5023
  mock_settings.log_level = "INFO"
  mock_settings.log_file = None
  mock_settings.threshold = 0.15
  mock_settings.cert_file = None
  mock_settings.key_file = None
  mock_settings.password = None
  mock_settings.model_path = "/mock/model.tflite"
  mock_settings.config = MagicMock()

  with (
    patch("ohunerin.parse_arguments", return_value=mock_args),
    patch("ohunerin.Settings", return_value=mock_settings),
    patch("ohunerin.Server", return_value=mock_server),
  ):
    await start()
    mock_server.listen.assert_called_once_with("127.0.0.1", 5023)


def test_main():
  with patch("ohunerin.start", new_callable=AsyncMock), patch("asyncio.run") as mock_run:
    main()
    mock_run.assert_called_once()


def test_main_keyboard_interrupt():
  with patch("asyncio.run", side_effect=KeyboardInterrupt):
    main()  # Should handle KeyboardInterrupt without raising


def test_main_exception_info_level():
  error = ValueError("Wakewords config file does not exist")
  expected_error = f"Oremi Ohunerin failed to start: {error}"

  with (
    patch("asyncio.run", side_effect=error),
    patch("ohunerin.logger.isEnabledFor", return_value=False),
    patch("ohunerin.logger.error") as mock_error,
    patch("sys.exit") as mock_exit,
  ):
    main()
    mock_error.assert_called_with(expected_error)
    mock_exit.assert_called_with(1)


def test_main_exception_debug_level():
  error = ValueError("Wakewords config file does not exist")
  with (
    patch("asyncio.run", side_effect=error),
    patch("ohunerin.logger.isEnabledFor", return_value=True),
    patch("ohunerin.logger.exception") as mock_exception,
    patch("sys.exit") as mock_exit,
  ):
    main()
    mock_exception.assert_called_once_with(error)
    mock_exit.assert_called_once_with(1)
