from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from macro_event_telegram_alerts.digest import DailyDigestService, format_digest
from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance, SignificancePolicy

UTC_NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
TZ = ZoneInfo("America/New_York")


def _event(title: str, when: datetime | None, day: date) -> MacroEvent:
    return MacroEvent(
        source_id=title.lower().replace(" ", "-"),
        title=title,
        institution="Test institution",
        source_url="https://example.com/calendar",
        scheduled_date=day,
        timing_precision=TimingPrecision.EXACT if when else TimingPrecision.DATE_ONLY,
        policy=SignificancePolicy(EventSignificance.SIGNIFICANT, "test"),
        retrieved_at=UTC_NOW,
        starts_at_local=when.astimezone(TZ) if when else None,
        starts_at_utc=when,
    )


def test_empty_digest_is_explicit() -> None:
    assert (
        format_digest([], 7) == "Macro digest - next 7 days\nNo upcoming events found."
    )


def test_digest_keeps_date_only_and_sorts_multiple_sources() -> None:
    later = _event("Later", UTC_NOW + timedelta(days=2), date(2026, 9, 19))
    date_only = _event("Date only", None, date(2026, 9, 18))
    earlier = _event("Earlier", UTC_NOW + timedelta(days=1), date(2026, 9, 18))
    text = format_digest([later, date_only, earlier], 7)
    assert text.index("Earlier") < text.index("Later")
    assert "2026-09-18 - Date only" in text
    assert "2026-09-18 08:00 UTC" in text
    assert "2026-09-18 04:00 EDT" in text


def test_daily_digest_is_sent_once_and_retries_after_failure(tmp_path: Path) -> None:
    service = DailyDigestService(
        tmp_path / "state.sqlite3", hour=9, minute=0, horizon_days=7
    )
    event = _event("Event", UTC_NOW + timedelta(days=1), date(2026, 9, 18))
    sent: list[str] = []
    assert not service.run([event], UTC_NOW, TZ, sent.append)
    due = datetime(2026, 9, 17, 14, 0, tzinfo=UTC)
    assert service.run([event], due, TZ, sent.append)
    assert not service.run([event], due + timedelta(minutes=1), TZ, sent.append)
    assert len(sent) == 1
