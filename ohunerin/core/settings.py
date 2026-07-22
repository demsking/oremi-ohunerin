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
import json
import logging
from functools import cached_property
from pathlib import Path
from typing import Any
from typing import Literal

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from ohunerin.core.package import DEFAULT_CONFIG_FILE
from ohunerin.core.package import DEFAULT_MODEL_PATH
from ohunerin.models.sound import SoundsConfig
from ohunerin.models.wakeword import WakewordsConfig

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
  """Application configuration settings for Oremi Ohunerin using Pydantic Settings."""

  model_config = SettingsConfigDict(
    env_prefix="OREMI_OHUNERIN_",
    strict=True,
    extra="ignore",
  )

  server_host: str = Field(default="127.0.0.1", description="Host address to listen on.")
  server_port: int = Field(default=5023, ge=1, le=65535, description="Port number to listen on.")

  cert_file: str | None = Field(default=None, description="Path to SSL certificate file.")
  key_file: str | None = Field(default=None, description="Path to SSL private key file.")
  password: str | None = Field(default=None, description="Password to unlock private key.")

  config_path: Path | None = Field(default=None, description="Path to unified configuration JSON file.")
  model_path: Path = Field(default=DEFAULT_MODEL_PATH, description="Path to audio classification model file.")
  threshold: float = Field(default=0.1, description="Default score threshold for detection.")

  log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO", description="Logging level.")
  log_file: str | None = Field(default=None, description="Path to rotating log file.")

  @cached_property
  def config(self) -> dict[str, Any]:
    if self.config_path and self.config_path.is_file():
      content = self.config_path.read_text().strip()

      if not content:
        raw: Any = {}
      else:
        try:
          raw = json.loads(content)
        except Exception as err:
          raise ValueError(f"Invalid JSON in config file {self.config_path}: {err}") from err

      if not isinstance(raw, dict):
        if isinstance(raw, list):
          raw = {"wakewords": raw}
        else:
          raw = {}
    else:
      raw = {}

    default_raw: dict[str, Any] = {}

    if self.config_path != DEFAULT_CONFIG_FILE:
      default_content = DEFAULT_CONFIG_FILE.read_text().strip()
      default_raw = json.loads(default_content)

    if "wakewords" not in raw and "wakewords" in default_raw:
      raw["wakewords"] = default_raw["wakewords"]

    if "sounds" not in raw and "sounds" in default_raw:
      raw["sounds"] = default_raw["sounds"]

    return raw

  @cached_property
  def wakewords_config(self) -> WakewordsConfig:
    """Load and parse the wakewords configuration file."""
    wakewords_data = self.config.get("wakewords", [])

    return WakewordsConfig.model_validate(wakewords_data)

  @cached_property
  def sounds_config(self) -> SoundsConfig:
    """Load and parse the sounds configuration file."""
    sounds_data = self.config.get("sounds", {})

    return SoundsConfig.model_validate(sounds_data)

  @field_validator("password", mode="before")
  @classmethod
  def validate_password(cls, value: Any) -> str | None:
    if value is None:
      return None

    value = str(value).strip()
    return value or None

  @field_validator("config_path", mode="before")
  @classmethod
  def validate_config_path(cls, value: Any) -> Path:
    return value if value and Path(value).expanduser().resolve().is_file() else DEFAULT_CONFIG_FILE

  @field_validator("model_path", mode="before")
  @classmethod
  def validate_model_path(cls, value: Any) -> Path:
    if value is None:
      value = DEFAULT_MODEL_PATH

    path = Path(value).expanduser().resolve()

    if not path.is_file():
      raise ValueError(f"Model file does not exist: {path}")

    return path

  @field_validator("cert_file", "key_file", "log_file", mode="before")
  @classmethod
  def validate_optional_paths(cls, value: Any) -> str | None:
    if value in (None, ""):
      return None

    return str(Path(value).expanduser().resolve())


def _format(value: Any) -> str:
  if value is None:
    return "None"

  if isinstance(value, Path):
    return str(value)

  if isinstance(value, bool):
    return str(value)

  return str(value)


def _password(value: str | None) -> str:
  return "<set>" if value else "<unset>"


def log_group(settings: Settings, name: str, *fields: str) -> None:
  values: list[str] = []

  for field in fields:
    value = getattr(settings, field)

    if field == "password":
      value = _password(value)
    else:
      value = _format(value)

    values.append(f"{field}={value}")

  logger.info("App settings [%s]: %s", name, " ".join(values))


def log_config_details(wakewords_config: WakewordsConfig, sounds_config: SoundsConfig) -> None:
  """Log a human-readable summary of the loaded configuration."""
  if wakewords_config.wakewords:
    by_lang: dict[str, list[str]] = {}

    for entry in wakewords_config.wakewords:
      by_lang.setdefault(entry.language, []).append(entry.word)
    for lang, words in by_lang.items():
      logger.info(f"Wakewords [{lang}]: {', '.join(words)}")
  else:
    logger.info("Wakewords: (none)")

  if sounds_config.allowlist:
    logger.info(f"Sounds allowlist ({len(sounds_config.allowlist)}): {', '.join(sounds_config.allowlist)}")

  if sounds_config.denylist:
    logger.info(f"Sounds denylist ({len(sounds_config.denylist)}): {', '.join(sounds_config.denylist)}")

  if not sounds_config.allowlist and not sounds_config.denylist:
    logger.info("Sounds: (none — all sounds accepted)")
