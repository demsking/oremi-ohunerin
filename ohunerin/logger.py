import os

from oremi_core.logger import Logger

from .package import APP_NAME

log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
log_file = os.environ.get('LOG_FILE')

Logger.set_global_level(log_level)

logger = Logger.create(APP_NAME, filename=log_file, level=log_level)
