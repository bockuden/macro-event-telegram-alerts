"""Exercise diagnostics through the real CLI without production side effects."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest

from macro_event_telegram_alerts import cli
from macro_event_telegram_alerts.app_config import SourceName
from macro_event_telegram_alerts.app_runtime import (
    ApplicationRunner,
    NamedProvider,
    inspect_source,
)
from macro_event_telegram_alerts.delivery_ledger import ReminderLedger
from macro_event_telegram_alerts.domain import MacroEvent
from macro_event_telegram_alerts.health import HealthReporter
from macro_event_telegram_alerts.providers import cached_http
from macro_event_telegram_alerts.providers.bls_calendar import BlsCalendarProvider
from macro_event_telegram_alerts.providers.bls_transport import BlsCalendarTransport
from macro_event_telegram_alerts.providers.cached_http import (
    HttpResult,
    TransportDiagnostics,
)
from macro_event_telegram_alerts.reminder_service import ReminderService
from macro_event_telegram_alerts.reminders import ReminderPolicy

NOW = datetime(2026, 9, 10, 10, tzinfo=UTC)
FIXTURE = Path(__file__).parent / "fixtures" / "bls-minimal.ics"


def config_file(tmp_path: Path) -> Path:
    text = (Path(__file__).parents[1] / "config.example.toml").read_text()
    text = text.replace('["bls", "bea", "fomc"]', '["bls"]')
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_cache_only_command_does_not_touch_secrets_network_or_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = config_file(tmp_path)
    (tmp_path / ".env").write_text("deliberately invalid secret file")

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("diagnostics touched delivery, secrets, or network")

    monkeypatch.setattr(cached_http, "_urllib_get", forbidden)
    monkeypatch.setattr(cli, "build_runner", forbidden)
    monkeypatch.setattr(cli, "load_dotenv", forbidden)
    monkeypatch.setattr(cli, "TelegramNotifier", forbidden)
    output = StringIO()
    status = cli.main(["diagnose-sources", "--config", str(path)], output=output)
    result = json.loads(output.getvalue())
    assert status == 1
    assert result["mode"] == "cache-only"
    source = result["sources"][0]
    assert source["category"] == "cache_missing"
    assert source["total_events"] is None
    assert not (tmp_path / "state").exists()
    assert "secret" not in output.getvalue()


def test_live_command_reports_403_without_changing_ledger_or_leaking_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = config_file(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    ledger = state / "reminders.sqlite3"
    ledger.write_bytes(b"existing delivery ledger sentinel")
    health = state / "health.json"
    health.write_bytes(b"existing health sentinel")
    monkeypatch.setattr(
        cached_http,
        "_urllib_get",
        lambda *_: HttpResult(
            403,
            b"secret-token recipient-id raw-response",
            {},
        ),
    )
    output = StringIO()
    status = cli.main(
        [
            "diagnose-sources",
            "--live",
            "--config",
            str(path),
        ],
        output=output,
    )
    source = json.loads(output.getvalue())["sources"][0]
    assert status == 1
    assert source["source"] == "bls"
    assert source["status"] == "failed"
    assert source["http_status"] == 403
    assert source["category"] == "http"
    assert "secret-token" not in output.getvalue()
    assert "recipient-id" not in output.getvalue()
    assert ledger.read_bytes() == b"existing delivery ledger sentinel"
    assert health.read_bytes() == b"existing health sentinel"


def test_live_probe_honors_cache_and_reports_future_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = config_file(tmp_path)
    calls: list[int] = []

    def http(*_: object) -> HttpResult:
        calls.append(1)
        return HttpResult(200, FIXTURE.read_bytes(), {"Content-Type": "text/calendar"})

    monkeypatch.setattr(cached_http, "_urllib_get", http)
    monkeypatch.setattr(cli, "utc_now", lambda: NOW)
    for expected_cached in (False, True):
        output = StringIO()
        status = cli.main(
            [
                "diagnose-sources",
                "--live",
                "--config",
                str(path),
            ],
            output=output,
        )
        source = json.loads(output.getvalue())["sources"][0]
        assert status == 0
        assert source["total_events"] == 4
        assert source["future_timed_events"] == 2
        assert source["next_event_at"] == "2026-09-10T12:30:00+00:00"
        assert source["from_cache"] is expected_cached
        assert source["next_request_at"] == "2026-09-10T16:00:00+00:00"
    assert calls == [1]
    assert not (tmp_path / "state" / "reminders.sqlite3").exists()


@pytest.mark.parametrize(
    "body,expected_status,expected_category",
    [
        (b"broken calendar secret-value", "failed", "parse"),
        (b"BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n", "healthy", None),
    ],
)
def test_empty_calendar_is_distinct_from_parse_failure(
    tmp_path: Path,
    body: bytes,
    expected_status: str,
    expected_category: str | None,
) -> None:
    transport = BlsCalendarTransport(
        cache_dir=tmp_path,
        user_agent="test (+https://example.org)",
        clock=lambda: NOW,
        http_get=lambda *_: HttpResult(200, body, {"Content-Type": "text/calendar"}),
    )
    _, report = inspect_source(
        NamedProvider(
            SourceName.BLS,
            BlsCalendarProvider(transport),
            transport.diagnostics,
        ),
        NOW,
    )
    assert report.status == expected_status
    assert report.transport.category == expected_category
    assert report.future_events == (0 if expected_status == "healthy" else None)
    assert "secret-value" not in str(report.to_dict())


def test_degraded_cache_does_not_refresh_health(tmp_path: Path) -> None:
    class EmptyProvider:
        def load(self) -> tuple[MacroEvent, ...]:
            return ()

    snapshot = replace(
        TransportDiagnostics(), stale=True, retrieved_at=NOW - timedelta(days=1)
    )
    health = tmp_path / "health.json"
    runner = ApplicationRunner(
        [NamedProvider(SourceName.BLS, EmptyProvider(), lambda: snapshot)],
        ReminderService(ReminderPolicy(), ReminderLedger(tmp_path / "ledger.sqlite3")),
        HealthReporter(health),
    )
    result = runner.run_once(NOW, lambda _: pytest.fail("unexpected delivery"))
    assert result.failed_sources == (SourceName.BLS,)
    assert not health.exists()


def test_service_logs_http_status_without_response_text(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = BlsCalendarTransport(
        cache_dir=tmp_path / "cache",
        user_agent="test (+https://example.org)",
        clock=lambda: NOW,
        http_get=lambda *_: HttpResult(403, b"private-message-body", {}),
    )
    runner = ApplicationRunner(
        [
            NamedProvider(
                SourceName.BLS, BlsCalendarProvider(transport), transport.diagnostics
            )
        ],
        ReminderService(ReminderPolicy(), ReminderLedger(tmp_path / "ledger.sqlite3")),
    )
    runner.run_once(NOW, lambda _: pytest.fail("unexpected delivery"))
    assert "source=bls" in caplog.text
    assert "http_status=403" in caplog.text
    assert "category=http" in caplog.text
    assert "private-message-body" not in caplog.text
