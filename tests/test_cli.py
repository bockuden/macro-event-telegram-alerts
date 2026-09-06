"""Deterministic command wiring tests with no source or Telegram network access."""

from datetime import datetime
from io import StringIO
from pathlib import Path

from macro_event_telegram_alerts.app_config import SourceName
from macro_event_telegram_alerts.cli import main


class _Result:
    @property
    def failed_sources(self) -> tuple[SourceName, ...]:
        return ()


class _Runner:
    def __init__(self) -> None:
        self.calls = 0

    def run_once(self, now: datetime, deliver: object) -> _Result:
        del now, deliver
        self.calls += 1
        return _Result()


def _config(tmp_path: Path, *, telegram: bool = False) -> Path:
    telegram_section = (
        """
[telegram]
chat_id = 42
token_env = "MACRO_EVENT_TELEGRAM_BOT_TOKEN"
"""
        if telegram
        else ""
    )
    path = tmp_path / "config.toml"
    path.write_text(
        """[application]
sources = ["bls"]
timezone = "UTC"
cache_dir = "cache"
ledger_path = "state.sqlite3"
source_poll_interval_minutes = 360
loop_interval_seconds = 60
"""
        + telegram_section,
        encoding="utf-8",
    )
    return path


def test_check_config_does_not_build_or_load_sources(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        ["check-config", "--config", str(_config(tmp_path))],
        runner_builder=lambda config, clock: (_ for _ in ()).throw(AssertionError()),
        output=output,
        error_output=StringIO(),
    )

    assert result == 0
    assert output.getvalue() == "Configuration is valid.\n"


def test_dry_run_requires_no_telegram_configuration_or_token(tmp_path: Path) -> None:
    runner = _Runner()

    result = main(
        ["dry-run", "--config", str(_config(tmp_path))],
        runner_builder=lambda config, clock: runner,
        environment={},
        output=StringIO(),
        error_output=StringIO(),
    )

    assert result == 0
    assert runner.calls == 1


def test_run_rejects_missing_token_before_building_sources(tmp_path: Path) -> None:
    errors = StringIO()

    result = main(
        ["run", "--once", "--config", str(_config(tmp_path, telegram=True))],
        runner_builder=lambda config, clock: (_ for _ in ()).throw(AssertionError()),
        environment={},
        output=StringIO(),
        error_output=errors,
    )

    assert result == 2
    assert "Telegram bot token is missing" in errors.getvalue()
    assert "MACRO_EVENT_TELEGRAM_BOT_TOKEN" not in errors.getvalue()
