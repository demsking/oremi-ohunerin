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

import logging
import traceback

import coloredlogs

__all__ = [
  'Trace',
]

_format = '%(asctime)s - %(name)s - %(levelname)-s - %(message)s'


class OremiFormatter(logging.Formatter):
  def __init__(
    self,
    fmt = _format,
    datefmt = '%Y-%m-%d %H:%M:%S',
    style = '%',
    validate = True,
  ):
    super().__init__(fmt, datefmt, style, validate) # type: ignore
    self.error_fmt = '%(asctime)s - %(name)s - %(levelname)-s - %(message)s'
    self.error_formatter = logging.Formatter(self.error_fmt, datefmt)

  def formatException(self, ei):
    tb = ''.join(traceback.format_exception(*ei))
    last_line = tb.strip().split('\n')[-1]
    file_name, line_number, function_name, _ = traceback.extract_tb(ei[2])[-1]
    return f'{last_line} (File: {file_name}, Function: {function_name}, Line: {line_number})'


_formatter = OremiFormatter()
_console_handler = logging.StreamHandler()

_console_handler.setFormatter(_formatter)
_instances: dict[str, 'Trace'] = {}


class Trace(logging.Logger):
  """
  Custom logger that extends the logging.Logger class.

  Attributes:
    name (str): The name of the logger.
  """
  _global_level = logging.DEBUG

  def __init__(self, name: str):
    super().__init__(name)

    self.setLevel(Trace._global_level)
    self.addHandler(_console_handler)

  @classmethod
  def set_global_level(cls, level: int):
    cls._global_level = level

  @classmethod
  def create(cls, name: str, level: int | None = None):
    """
    Creates a Trace logger instance with the specified name.

    Args:
      name (str): The name of the logger.
      level (int): The logger level.

    Returns:
      Trace: A Trace logger instance.
    """
    if name not in _instances:
      logger = cls(name)
      _instances[name] = logger

      coloredlogs.install(
        logger = logger,
        fmt = _format,
        level = level or cls._global_level,
      )

    return _instances[name]

  def clone(self, name: str):
    """
    Clones the Trace logger with a new name.

    Args:
      name (str): The name of the cloned logger.

    Returns:
      Trace: A cloned Trace logger instance with the new name.
    """
    return Trace.create(f'{self.name} - {name}')
