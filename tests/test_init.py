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
import sys
from unittest.mock import MagicMock, patch
import pytest
from ohunerin import main, start


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
  mock_server.model_path = "/mock/model.tflite"

  with patch("ohunerin.parse_arguments", return_value=mock_args), \
       patch("ohunerin.Server", return_value=mock_server):
    await start()
    mock_server.listen.assert_called_once_with("127.0.0.1", 5023)


def test_main():
  with patch("ohunerin.start") as mock_start, \
       patch("asyncio.run") as mock_run:
    main()
    mock_run.assert_called_once()
