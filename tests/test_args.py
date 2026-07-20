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
from unittest.mock import patch

from ohunerin.args import parse_arguments


def test_parse_arguments_defaults():
  with patch.object(sys, 'argv', ['oremi-ohunerin']):
    args = parse_arguments()
    assert args.config is None
    assert args.host == '127.0.0.1'
    assert args.port == 5023
    assert args.cert_file is None
    assert args.key_file is None
    assert args.password is None


def test_parse_arguments_custom():
  with patch.object(sys, 'argv', [
    'oremi-ohunerin',
    '-c', 'my_config.json',
    '--host', '0.0.0.0',
    '-p', '8080',
    '--cert-file', 'cert.pem',
    '--key-file', 'key.pem',
    '--password', 'secret'
  ]):
    args = parse_arguments()
    assert args.config == 'my_config.json'
    assert args.host == '0.0.0.0'
    assert args.port == 8080
    assert args.cert_file == 'cert.pem'
    assert args.key_file == 'key.pem'
    assert args.password == 'secret'
