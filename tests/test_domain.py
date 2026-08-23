"""Tests for normalized macro-event invariants."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from macro_event_telegram_alerts import (
    EventSignificance,
    MacroEvent,
    SignificancePolicy,
    TimingPrecision,
)


def _policy() -> SignificancePolicy:
    return SignificancePolicy(
        significance=EventSignificance.SIGNIFICANT,
        revision="us-major-events-v1",
    )


def _exact_event(**changes: object) -> MacroEvent:
    values: dict[str, object] = {
        "source_id": "bls:cpi:2026-09-15",
        "title": "Consumer Price Index",
        "institution": "U.S. Bureau of Labor Statistics",
        "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
        "scheduled_date": date(2026, 9, 15),
        "timing_precision": TimingPrecision.EXACT,
        "policy": _policy(),
        "retrieved_at": datetime(2026, 8, 23, 9, tzinfo=UTC),
        "starts_at_local": datetime(
            2026,
            9,
            15,
            8,
            30,
            tzinfo=ZoneInfo("America/New_York"),
        ),
        "starts_at_utc": datetime(2026, 9, 15, 12, 30, tzinfo=UTC),
    }
    values.update(changes)
    return MacroEvent(**values)  # type: ignore[arg-type]


def test_exact_event_retains_source_and_normalized_times() -> None:
    event = _exact_event()

    assert event.starts_at_local is not None
    assert event.starts_at_local.tzinfo == ZoneInfo("America/New_York")
    assert event.starts_at_utc == datetime(2026, 9, 15, 12, 30, tzinfo=UTC)
    assert event.retrieved_at == datetime(2026, 8, 23, 9, tzinfo=UTC)
    assert event.policy.significance is EventSignificance.SIGNIFICANT
    assert event.policy.revision == "us-major-events-v1"


def test_date_only_event_does_not_invent_an_instant() -> None:
    event = MacroEvent(
        source_id="bea:gdp:2026-09-30",
        title="Gross Domestic Product",
        institution="U.S. Bureau of Economic Analysis",
        source_url="https://www.bea.gov/news/schedule",
        scheduled_date=date(2026, 9, 30),
        timing_precision=TimingPrecision.DATE_ONLY,
        policy=_policy(),
        retrieved_at=datetime(2026, 8, 23, 9, tzinfo=UTC),
    )

    assert event.starts_at_local is None
    assert event.starts_at_utc is None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"starts_at_local": datetime(2026, 9, 15, 8, 30)},
            "starts_at_local must be timezone-aware",
        ),
        (
            {"starts_at_utc": datetime(2026, 9, 15, 13, 30, tzinfo=UTC)},
            "must represent one instant",
        ),
        (
            {"retrieved_at": datetime(2026, 8, 23, 9)},
            "retrieved_at must be timezone-aware",
        ),
    ],
)
def test_event_rejects_invalid_time_invariants(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _exact_event(**changes)


def test_date_only_event_rejects_an_invented_instant() -> None:
    with pytest.raises(ValueError, match="date_only timing precision"):
        _exact_event(timing_precision=TimingPrecision.DATE_ONLY)


def test_policy_requires_a_traceable_revision() -> None:
    with pytest.raises(ValueError, match="policy revision"):
        SignificancePolicy(
            significance=EventSignificance.SIGNIFICANT,
            revision=" ",
        )
