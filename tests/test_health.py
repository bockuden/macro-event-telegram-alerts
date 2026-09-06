"""Tests for durable service-loop health state."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from macro_event_telegram_alerts.health import (
    HealthReporter,
    HealthStateError,
    require_recent_success,
)


def test_recent_success_is_healthy(tmp_path: Path) -> None:
    path = tmp_path / "state" / "health.json"
    now = datetime(2026, 9, 6, 12, tzinfo=UTC)
    HealthReporter(path).record_success(now)

    require_recent_success(
        path, now=now + timedelta(seconds=60), max_age=timedelta(minutes=2)
    )


def test_missing_or_stale_state_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    now = datetime(2026, 9, 6, 12, tzinfo=UTC)

    with pytest.raises(HealthStateError, match="unavailable"):
        require_recent_success(path, now=now, max_age=timedelta(minutes=1))

    HealthReporter(path).record_success(now)
    with pytest.raises(HealthStateError, match="stale"):
        require_recent_success(
            path,
            now=now + timedelta(minutes=2),
            max_age=timedelta(minutes=1),
        )
