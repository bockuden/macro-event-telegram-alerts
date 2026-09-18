from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from macro_event_telegram_alerts import cli
from macro_event_telegram_alerts.app_config import load_config
from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance, SignificancePolicy
from macro_event_telegram_alerts.providers.cached_http import TransportDiagnostics
from macro_event_telegram_alerts.source_diagnostics import SourceReport


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        """[application]
sources = ["bls"]
timezone = "UTC"
cache_dir = "cache"
ledger_path = "state.sqlite3"
source_poll_interval_minutes = 360
loop_interval_seconds = 60
""",
        encoding="utf-8",
    )
    return path


def _event(title: str, days: int) -> MacroEvent:
    when = datetime(2026, 9, 18, 12, tzinfo=UTC) + timedelta(days=days)
    return MacroEvent(
        source_id=title.lower(),
        title=title,
        institution="Test institution",
        source_url="https://example.com/source",
        scheduled_date=when.date(),
        timing_precision=TimingPrecision.EXACT,
        policy=SignificancePolicy(EventSignificance.SIGNIFICANT, "test"),
        retrieved_at=datetime(2026, 9, 17, tzinfo=UTC),
        starts_at_local=when,
        starts_at_utc=when,
    )


def test_preview_orders_and_filters_events_without_building_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = _config(tmp_path)
    config = load_config(config_path)
    now = datetime(2026, 9, 17, 12, tzinfo=UTC)
    events = (_event("Later", 2), _event("Earlier", 1), _event("Outside", 10))
    report = SourceReport("bls", "healthy", TransportDiagnostics(), 0, 3, 3, 3, None)
    monkeypatch.setattr(cli, "utc_now", lambda: now)
    monkeypatch.setattr(
        cli,
        "build_official_providers",
        lambda config, clock, allow_network: (SimpleNamespace(name="bls"),),
    )
    monkeypatch.setattr(
        cli, "inspect_source", lambda provider, current: (events, report)
    )

    output = StringIO()
    assert cli._preview(config, 7, output, StringIO()) == 0
    text = output.getvalue()
    assert text.index("Earlier") < text.index("Later")
    assert "Outside" not in text
    assert "2026-09-19 12:00 UTC" in text


def test_preview_reports_empty_calendar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(_config(tmp_path))
    report = SourceReport("bls", "healthy", TransportDiagnostics(), 0, 0, 0, 0, None)
    monkeypatch.setattr(
        cli,
        "build_official_providers",
        lambda *args, **kwargs: (SimpleNamespace(name="bls"),),
    )
    monkeypatch.setattr(cli, "inspect_source", lambda provider, current: ((), report))
    output = StringIO()
    assert cli._preview(config, 7, output, StringIO()) == 0
    assert "No upcoming events found." in output.getvalue()
