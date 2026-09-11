"""Validated TOML configuration for the runnable reminder application."""

import tomllib
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from macro_event_telegram_alerts.reminders import DEFAULT_LEAD_TIMES, ReminderPolicy


class ConfigError(ValueError):
    """A configuration file is incomplete, invalid, or unsafe to use."""


class SourceName(StrEnum):
    """Official source adapters supported by the first runnable application."""

    BLS = "bls"
    BEA = "bea"
    FOMC = "fomc"


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    """Telegram environment-variable names and optional token-file location."""

    chat_id_env: str
    token_env: str | None
    token_file: Path | None


@dataclass(frozen=True, slots=True)
class AppConfig:
    """All non-secret settings required to run the single process."""

    sources: tuple[SourceName, ...]
    timezone: ZoneInfo
    cache_dir: Path
    ledger_path: Path
    health_path: Path
    source_poll_interval: timedelta
    source_rejection_cooldown: timedelta
    source_retry_max_backoff: timedelta
    source_max_stale_cache_age: timedelta
    loop_interval: timedelta
    reminder_policy: ReminderPolicy
    telegram: TelegramConfig | None


def load_config(path: Path) -> AppConfig:
    """Load TOML without performing network requests or reading secrets."""
    try:
        document: object = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigError("configuration file could not be read") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError("configuration file is not valid TOML") from error
    if not isinstance(document, dict):
        raise ConfigError("configuration root must be a TOML table")
    _reject_unknown_keys(document, {"application", "telegram"}, "configuration")
    application = _table(
        _required(document, "application", "configuration"), "application"
    )
    _reject_unknown_keys(
        application,
        {
            "sources",
            "timezone",
            "cache_dir",
            "ledger_path",
            "health_path",
            "source_poll_interval_minutes",
            "source_rejection_cooldown_minutes",
            "source_retry_max_backoff_minutes",
            "source_max_stale_cache_hours",
            "loop_interval_seconds",
            "reminder_lead_minutes",
        },
        "application",
    )
    base_dir = path.parent.resolve()
    ledger_path = _path(
        _required(application, "ledger_path", "application"),
        base_dir,
        "ledger_path",
    )
    health_path = _path(
        application.get("health_path", str(ledger_path.parent / "health.json")),
        base_dir,
        "health_path",
    )
    source_poll_interval = _positive_minutes(
        _required(application, "source_poll_interval_minutes", "application"),
        "source_poll_interval_minutes",
    )
    source_retry_max_backoff = _positive_minutes(
        application.get("source_retry_max_backoff_minutes", 1440),
        "source_retry_max_backoff_minutes",
    )
    if source_retry_max_backoff < source_poll_interval:
        raise ConfigError(
            "application.source_retry_max_backoff_minutes must not be shorter "
            "than source_poll_interval_minutes"
        )
    return AppConfig(
        sources=_sources(_required(application, "sources", "application")),
        timezone=_timezone(_required(application, "timezone", "application")),
        cache_dir=_path(
            _required(application, "cache_dir", "application"), base_dir, "cache_dir"
        ),
        ledger_path=ledger_path,
        health_path=health_path,
        source_poll_interval=source_poll_interval,
        source_rejection_cooldown=_positive_minutes(
            application.get("source_rejection_cooldown_minutes", 360),
            "source_rejection_cooldown_minutes",
        ),
        source_retry_max_backoff=source_retry_max_backoff,
        source_max_stale_cache_age=_positive_hours(
            application.get("source_max_stale_cache_hours", 168),
            "source_max_stale_cache_hours",
        ),
        loop_interval=_positive_seconds(
            _required(application, "loop_interval_seconds", "application"),
            "loop_interval_seconds",
        ),
        reminder_policy=ReminderPolicy(
            tuple(
                timedelta(minutes=minutes)
                for minutes in _positive_integer_list(
                    application.get("reminder_lead_minutes"),
                    "reminder_lead_minutes",
                    default=tuple(
                        int(lead_time.total_seconds() // 60)
                        for lead_time in DEFAULT_LEAD_TIMES
                    ),
                )
            )
        ),
        telegram=_telegram_config(document.get("telegram"), base_dir),
    )


def _sources(value: object) -> tuple[SourceName, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError("application.sources must be a non-empty list")
    try:
        sources = tuple(
            SourceName(_string(item, "application.sources")) for item in value
        )
    except ValueError as error:
        raise ConfigError(
            "application.sources contains an unsupported source"
        ) from error
    if len(set(sources)) != len(sources):
        raise ConfigError("application.sources must not contain duplicates")
    return sources


def _timezone(value: object) -> ZoneInfo:
    name = _string(value, "application.timezone")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise ConfigError("application.timezone is not an IANA timezone") from error


def _path(value: object, base_dir: Path, name: str) -> Path:
    raw = _string(value, f"application.{name}")
    if not raw.strip():
        raise ConfigError(f"application.{name} must not be empty")
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else base_dir / candidate


def _positive_minutes(value: object, name: str) -> timedelta:
    return timedelta(minutes=_positive_integer(value, f"application.{name}"))


def _positive_seconds(value: object, name: str) -> timedelta:
    return timedelta(seconds=_positive_integer(value, f"application.{name}"))


def _positive_hours(value: object, name: str) -> timedelta:
    return timedelta(hours=_positive_integer(value, f"application.{name}"))


def _positive_integer_list(
    value: object,
    name: str,
    *,
    default: tuple[int, ...],
) -> tuple[int, ...]:
    if value is None:
        return default
    if not isinstance(value, list) or not value:
        raise ConfigError(f"application.{name} must be a non-empty list")
    return tuple(_positive_integer(item, f"application.{name}") for item in value)


def _positive_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return value


def _telegram_config(value: object, base_dir: Path) -> TelegramConfig | None:
    if value is None:
        return None
    telegram = _table(value, "telegram")
    _reject_unknown_keys(
        telegram, {"chat_id_env", "token_env", "token_file"}, "telegram"
    )
    chat_id_env = _string(
        _required(telegram, "chat_id_env", "telegram"), "telegram.chat_id_env"
    )
    if not chat_id_env.strip():
        raise ConfigError("telegram.chat_id_env must not be empty")
    token_env = telegram.get("token_env")
    token_file = telegram.get("token_file")
    if token_env is not None and token_file is not None:
        raise ConfigError("telegram must specify only one token location")
    if token_env is not None:
        token_env = _string(token_env, "telegram.token_env")
        if not token_env.strip():
            raise ConfigError("telegram.token_env must not be empty")
    resolved_token_file = (
        _path_from_section(token_file, base_dir, "telegram.token_file")
        if token_file is not None
        else None
    )
    if token_env is None and resolved_token_file is None:
        raise ConfigError("telegram must specify token_env or token_file")
    return TelegramConfig(chat_id_env, token_env, resolved_token_file)


def _path_from_section(value: object, base_dir: Path, name: str) -> Path:
    raw = _string(value, name)
    if not raw.strip():
        raise ConfigError(f"{name} must not be empty")
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else base_dir / candidate


def _required(table: dict[str, object], name: str, section: str) -> object:
    try:
        return table[name]
    except KeyError as error:
        raise ConfigError(f"{section}.{name} is required") from error


def _table(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigError(f"{name} must be a TOML table")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{name} must be a string")
    return value


def _reject_unknown_keys(
    table: dict[str, object], allowed: set[str], name: str
) -> None:
    if unknown := set(table) - allowed:
        raise ConfigError(
            f"{name} contains unsupported settings: {', '.join(sorted(unknown))}"
        )
