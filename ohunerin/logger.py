# Copyright 2025 Sébastien Demanou. All Rights Reserved.
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
import logging
import os

from oremi_core.logger import Logger

from .package import APP_NAME

# Map log level strings to their corresponding integer values
LOG_LEVEL_MAP = {
  'DEBUG': logging.DEBUG,
  'INFO': logging.INFO,
  'WARNING': logging.WARNING,
  'ERROR': logging.ERROR,
  'CRITICAL': logging.CRITICAL,
}

# Get log level from environment variable or default to 'INFO'
LOG_LEVEL_STR = os.environ.get('LOG_LEVEL', 'INFO').upper()
log_file = os.environ.get('LOG_FILE')

# Convert log level string to integer
log_level = LOG_LEVEL_MAP.get(LOG_LEVEL_STR, logging.INFO)  # Default to INFO if invalid

# Set global log level and create logger
Logger.set_global_level(log_level)  # type: ignore
logger = Logger.create(APP_NAME, filename=log_file, level=log_level)
