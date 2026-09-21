from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from macro_event_telegram_alerts import cli
from macro_event_telegram_alerts.app_config import load_config
from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import (
    EventImportance,
    EventSignificance,
    SignificancePolicy,
    importance_at_least,
)
from macro_event_telegram_alerts.providers.cached_http import TransportDiagnostics
from macro_event_telegram_alerts.source_diagnostics import SourceReport


def _config(tmp_path: Path, minimum: str = "medium") -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f"""[application]
sources = ["bls"]
timezone = "UTC"
cache_dir = "cache"
ledger_path = "state.sqlite3"
source_poll_interval_minutes = 360
loop_interval_seconds = 60
minimum_importance = "{minimum}"
""",
        encoding="utf-8",
    )
    return path


def _event(title: str, importance: EventImportance) -> MacroEvent:
    when = datetime(2026, 9, 22, 12, tzinfo=UTC)
    return MacroEvent(
        source_id=title,
        title=title,
        institution="Test institution",
        source_url="https://example.com/source",
        scheduled_date=when.date(),
        timing_precision=TimingPrecision.EXACT,
        policy=SignificancePolicy(EventSignificance.SIGNIFICANT, "test", importance),
        retrieved_at=datetime(2026, 9, 20, tzinfo=UTC),
        starts_at_local=when,
        starts_at_utc=when,
    )


def test_importance_filter_is_project_policy() -> None:
    assert importance_at_least(
        SignificancePolicy(EventSignificance.SIGNIFICANT, "test", EventImportance.HIGH),
        EventImportance.HIGH,
    )
    assert not importance_at_least(
        SignificancePolicy(
            EventSignificance.SIGNIFICANT, "test", EventImportance.MEDIUM
        ),
        EventImportance.HIGH,
    )


def test_status_reports_source_health_filter_and_missing_telegram(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(_config(tmp_path, "high"))
    events = (
        _event("high-event", EventImportance.HIGH),
        _event("medium-event", EventImportance.MEDIUM),
    )
    report = SourceReport(
        "bls",
        "degraded",
        TransportDiagnostics(active_source="new_york_fed"),
        0,
        2,
        2,
        2,
        events[0].starts_at_utc,
    )
    monkeypatch.setattr(cli, "utc_now", lambda: datetime(2026, 9, 20, tzinfo=UTC))
    monkeypatch.setattr(
        cli,
        "build_official_providers",
        lambda *args, **kwargs: (SimpleNamespace(name="bls"),),
    )
    monkeypatch.setattr(cli, "inspect_source", lambda provider, now: (events, report))
    output = StringIO()
    error = StringIO()
    assert cli._status(config, output, error, {}) == 1
    text = output.getvalue()
    assert "Source bls: degraded" in text
    assert "Fallback coverage: new_york_fed" in text
    assert "Future events: 1" in text
    assert "Telegram configuration: missing" in text
    assert "bls status: degraded" in error.getvalue()
