
"""Configuration loading utilities."""

import json
from pathlib import Path

import pydantic
from loguru import logger

from nanobot.config.schema import Config


# Current configuration path for instance-level runtime data.
_current_config_path: Path | None = None


def set_config_path(path: Path) -> None:
    """Set the active configuration file path."""
    global _current_config_path
    _current_config_path = path


def get_config_path() -> Path:
    """Return the active or default configuration file path."""
    if _current_config_path is not None:
        return _current_config_path

    return Path.home() / ".nanobot" / "config.json"


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from JSON or return default configuration."""
    path = config_path if config_path is not None else get_config_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            return Config.model_validate(data)

        except (json.JSONDecodeError, ValueError, pydantic.ValidationError) as e:
            logger.warning("Failed to load config from {}: {}", path, e)
            logger.warning("Using default configuration.")

    return Config()


def save_config(
    config: Config,
    config_path: Path | None = None,
) -> None:
    """Save configuration to a UTF-8 JSON file."""
    path = config_path if config_path is not None else get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(mode="json", by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)