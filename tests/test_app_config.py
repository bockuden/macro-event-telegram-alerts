"""Tests for non-secret TOML application configuration."""

from pathlib import Path

import pytest

from macro_event_telegram_alerts.app_config import ConfigError, SourceName, load_config


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_loads_cross_platform_relative_paths_and_optional_defaults(
    tmp_path: Path,
) -> None:
    config = load_config(
        _write_config(
            tmp_path,
            """[application]
sources = ["bls", "fomc"]
timezone = "Europe/Chisinau"
cache_dir = "state/cache"
ledger_path = "state/reminders.sqlite3"
source_poll_interval_minutes = 360
loop_interval_seconds = 60
""",
        )
    )

    assert config.sources == (SourceName.BLS, SourceName.FOMC)
    assert config.cache_dir == tmp_path / "state" / "cache"
    assert config.ledger_path == tmp_path / "state" / "reminders.sqlite3"
    assert config.health_path == tmp_path / "state" / "health.json"
    assert config.source_rejection_cooldown.total_seconds() == 6 * 60 * 60
    assert config.source_retry_max_backoff.total_seconds() == 24 * 60 * 60
    assert config.source_max_stale_cache_age.total_seconds() == 7 * 24 * 60 * 60
    assert [
        int(lead.total_seconds() // 60) for lead in config.reminder_policy.lead_times
    ] == [
        1440,
        60,
        15,
    ]
    assert config.telegram is None


def test_telegram_configuration_keeps_only_secret_location(tmp_path: Path) -> None:
    config = load_config(
        _write_config(
            tmp_path,
            """[application]
sources = ["bea"]
timezone = "UTC"
cache_dir = "cache"
ledger_path = "state.sqlite3"
source_poll_interval_minutes = 360
loop_interval_seconds = 60

[telegram]
chat_id_env = "MACRO_EVENT_TELEGRAM_CHAT_ID"
token_file = "secrets/bot-token"
""",
        )
    )

    assert config.telegram is not None
    assert config.telegram.chat_id_env == "MACRO_EVENT_TELEGRAM_CHAT_ID"
    assert config.telegram.token_file == tmp_path / "secrets" / "bot-token"
    assert config.telegram.token_env is None


@pytest.mark.parametrize(
    ("original", "replacement", "message"),
    [
        ('sources = ["bls"]', 'sources = ["bls", "bls"]', "duplicates"),
        ('timezone = "Europe/Chisinau"', 'timezone = "Mars/Olympus"', "IANA"),
        ("loop_interval_seconds = 60", "loop_interval_seconds = 0", "positive"),
    ],
)
def test_rejects_invalid_application_settings(
    tmp_path: Path, original: str, replacement: str, message: str
) -> None:
    path = _write_config(
        tmp_path,
        """[application]
sources = ["bls"]
timezone = "Europe/Chisinau"
cache_dir = "cache"
ledger_path = "state.sqlite3"
source_poll_interval_minutes = 360
loop_interval_seconds = 60
""".replace(original, replacement),
    )

    with pytest.raises(ConfigError, match=message):
        load_config(path)


def test_rejects_token_value_instead_of_a_secret_location(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """[application]
sources = ["bls"]
timezone = "UTC"
cache_dir = "cache"
ledger_path = "state.sqlite3"
source_poll_interval_minutes = 360
loop_interval_seconds = 60

[telegram]
chat_id_env = "MACRO_EVENT_TELEGRAM_CHAT_ID"
token = "do-not-store-me"
""",
    )

    with pytest.raises(ConfigError, match="unsupported settings") as caught:
        load_config(path)

    assert "do-not-store-me" not in str(caught.value)


def test_loads_source_cooldown_policy(tmp_path: Path) -> None:
    config = load_config(
        _write_config(
            tmp_path,
            """[application]
sources = ["bls"]
timezone = "UTC"
cache_dir = "cache"
ledger_path = "state.sqlite3"
source_poll_interval_minutes = 30
source_rejection_cooldown_minutes = 180
source_retry_max_backoff_minutes = 240
source_max_stale_cache_hours = 48
loop_interval_seconds = 60
""",
        )
    )

    assert config.source_rejection_cooldown.total_seconds() == 3 * 60 * 60
    assert config.source_retry_max_backoff.total_seconds() == 4 * 60 * 60
    assert config.source_max_stale_cache_age.total_seconds() == 48 * 60 * 60
