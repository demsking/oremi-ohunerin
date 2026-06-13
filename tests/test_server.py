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
import asyncio
import http
import json
import logging
import os
import pytest
from websockets.datastructures import Headers
from ohunerin.server import Server


@pytest.fixture
def logger():
  return logging.getLogger("test_server")


@pytest.fixture
def config_file():
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  return os.path.join(base_dir, "ohunerin", "config.json")


@pytest.mark.asyncio
async def test_server_info_endpoint(config_file, logger):
  server = Server(
    config_file=config_file,
    threshold=0.1,
    logger=logger,
  )

  headers = Headers()
  response = await server.process_http_request("/", headers)
  assert response is not None
  status, resp_headers, body = response

  assert status == http.HTTPStatus.OK

  # Check headers
  headers_dict = dict(resp_headers)
  assert headers_dict["Content-Type"] == "application/json; charset=utf-8"
  assert headers_dict["Access-Control-Allow-Origin"] == "*"

  # Check body
  data = json.loads(body.decode("utf-8"))
  assert data["name"] == "oremi-ohunerin"
  assert "version" in data
  assert data["threshold"] == 0.1
  assert "languages" not in data
  assert "wakewords" in data
  assert "oremi" in data["wakewords"]["fr"]
  assert "oremi" in data["wakewords"]["en"]


@pytest.mark.asyncio
async def test_other_endpoints(config_file, logger):
  server = Server(
    config_file=config_file,
    threshold=0.1,
    logger=logger,
  )

  # Test openapi.json
  response = await server.process_http_request("/openapi.json", Headers())
  assert response is not None
  status, _, body = response
  assert status == http.HTTPStatus.OK
  data = json.loads(body.decode("utf-8"))
  assert data["openapi"] == "3.0.0"

  # Test docs
  response = await server.process_http_request("/docs", Headers())
  assert response is not None
  status, _, body = response
  assert status == http.HTTPStatus.OK
  assert b"<!DOCTYPE html>" in body or b"html" in body.lower()

  # Test ws
  response = await server.process_http_request("/ws", Headers())
  assert response is None

  # Test not found
  response = await server.process_http_request("/invalid", Headers())
  assert response is not None
  status, _, body = response
  assert status == http.HTTPStatus.NOT_FOUND
  assert body == b"Not Found"
