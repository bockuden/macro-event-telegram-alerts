"""Local secret loading without logging or storing secret values in configuration."""

import os
from collections.abc import MutableMapping
from pathlib import Path

from macro_event_telegram_alerts.app_config import ConfigError, TelegramConfig


def load_dotenv(path: Path, environment: MutableMapping[str, str]) -> None:
    """Load simple KEY=VALUE entries without overwriting existing variables."""
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ConfigError("environment file could not be read") from error
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(
                f"environment file has invalid entry at line {line_number}"
            )
        name, value = line.split("=", maxsplit=1)
        if not name or not name.replace("_", "a").isalnum() or name[0].isdigit():
            raise ConfigError(
                f"environment file has invalid entry at line {line_number}"
            )
        environment.setdefault(name, _unquote(value.strip()))


def resolve_telegram_token(
    config: TelegramConfig | None,
    environment: MutableMapping[str, str] | None = None,
) -> str:
    """Read a configured token only when live Telegram delivery is requested."""
    if config is None:
        raise ConfigError("telegram configuration is required for run")
    environment = environment if environment is not None else os.environ
    if config.token_env is not None:
        token = environment.get(config.token_env, "")
    else:
        assert config.token_file is not None
        try:
            token = config.token_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ConfigError("telegram token file could not be read") from error
    if not token.strip():
        raise ConfigError("Telegram bot token is missing")
    return token


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
