"""Tests for local secret files and safe token resolution."""

from pathlib import Path

import pytest

from macro_event_telegram_alerts.app_config import ConfigError, TelegramConfig
from macro_event_telegram_alerts.secrets import load_dotenv, resolve_telegram_token


def test_dotenv_preserves_existing_environment_values(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("TOKEN=from-file\nOTHER='value'\n", encoding="utf-8")
    environment = {"TOKEN": "from-environment"}

    load_dotenv(path, environment)

    assert environment == {"TOKEN": "from-environment", "OTHER": "value"}


def test_missing_live_token_has_a_secret_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MACRO_EVENT_TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(ConfigError) as caught:
        resolve_telegram_token(
            TelegramConfig(42, "MACRO_EVENT_TELEGRAM_BOT_TOKEN", None)
        )

    assert "MACRO_EVENT_TELEGRAM_BOT_TOKEN" not in str(caught.value)


def test_token_file_is_read_only_when_live_delivery_is_requested(
    tmp_path: Path,
) -> None:
    token_file = tmp_path / "bot-token"
    token_file.write_text("test-token\n", encoding="utf-8")

    assert resolve_telegram_token(TelegramConfig(42, None, token_file)) == "test-token"
