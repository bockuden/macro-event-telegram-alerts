from datetime import UTC, datetime
from pathlib import Path

from macro_event_telegram_alerts.operational_incidents import OperationalIncidentStore


def test_incident_is_opened_once_persisted_and_then_recovered(tmp_path: Path) -> None:
    path = tmp_path / "incidents.json"
    now = datetime(2026, 9, 12, 12, tzinfo=UTC)
    store = OperationalIncidentStore(path)

    assert store.observe("bls", degraded=True, now=now).kind == "opened"
    assert store.observe("bls", degraded=True, now=now) is None
    restarted = OperationalIncidentStore(path)
    assert restarted.observe("bls", degraded=True, now=now) is None
    assert restarted.observe("bls", degraded=False, now=now).kind == "recovered"
