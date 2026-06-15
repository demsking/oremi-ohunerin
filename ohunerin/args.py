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
import argparse

from .package import APP_DESCRIPTION
from .package import APP_NAME
from .package import APP_VERSION


def parse_arguments():
  parser = argparse.ArgumentParser(prog=APP_NAME, description=APP_DESCRIPTION)

  parser.add_argument(
    '-c', '--config',
    type=str,
    default=None,
    help='Path to the configuration file.'
  )

  parser.add_argument(
    '--host',
    type=str,
    default='127.0.0.1',
    help='Host address to listen on (default: 127.0.0.1).'
  )

  parser.add_argument(
    '-p', '--port',
    type=int,
    default=5023,
    help='Port number to listen on (default: 5023).'
  )

  parser.add_argument(
    '--cert-file',
    type=str,
    help='Path to the certificate file for secure connection.',
  )

  parser.add_argument(
    '--key-file',
    type=str,
    help='Path to the private key file for secure connection.',
  )

  parser.add_argument(
    '--password',
    type=str,
    help='Password to unlock the private key (if protected by a password).',
  )

  parser.add_argument(
    '-v', '--version',
    action='version',
    version=f'%(prog)s {APP_VERSION}',
    help='Show the version of the application.'
  )

  return parser.parse_args()
