"""Offline Telegram Bot API notifier tests."""

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from macro_event_telegram_alerts import (
    EventSignificance,
    MacroEvent,
    SignificancePolicy,
    TimingPrecision,
)
from macro_event_telegram_alerts.reminders import Reminder
from macro_event_telegram_alerts.telegram_notifier import (
    HttpResponse,
    TelegramDeliveryError,
    TelegramNotifier,
)


class _FakeHttp:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, Mapping[str, str], bytes, float]] = []

    def __call__(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls.append((url, headers, body, timeout_seconds))
        return self.response


def _reminder() -> Reminder:
    local_time = datetime(2026, 9, 15, 8, 30, tzinfo=ZoneInfo("America/New_York"))
    event = MacroEvent(
        source_id="bls:cpi:2026-09-15",
        title="Consumer Price Index",
        institution="U.S. Bureau of Labor Statistics",
        source_url="https://www.bls.gov/news.release/cpi.nr0.htm",
        scheduled_date=date(2026, 9, 15),
        timing_precision=TimingPrecision.EXACT,
        policy=SignificancePolicy(EventSignificance.SIGNIFICANT, "us-major-events-v1"),
        retrieved_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
        starts_at_local=local_time,
        starts_at_utc=local_time.astimezone(UTC),
    )
    return Reminder(event=event, lead_time=timedelta(minutes=15))


def test_notifier_posts_json_with_a_bounded_timeout() -> None:
    http = _FakeHttp(HttpResponse(200, b'{"ok": true, "result": {}}', {}))
    notifier = TelegramNotifier(
        "123456:secret-token",
        -1001234567890,
        timeout_seconds=8,
        http_post=http,
    )

    notifier.deliver(_reminder())

    url, headers, body, timeout = http.calls[0]
    assert url == "https://api.telegram.org/bot123456:secret-token/sendMessage"
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert timeout == 8
    payload = json.loads(body)
    assert payload["chat_id"] == -1001234567890
    assert isinstance(payload["text"], str)
    assert "Consumer Price Index" in payload["text"]


@pytest.mark.parametrize("timeout", [0, -1, 30.1])
def test_notifier_rejects_unbounded_timeouts(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        TelegramNotifier("123456:secret-token", 42, timeout_seconds=timeout)


def test_failure_never_includes_token_or_chat_id() -> None:
    token = "123456:secret-token"
    chat_id = "private-recipient"
    http = _FakeHttp(HttpResponse(403, b'{"ok":false}', {}))
    notifier = TelegramNotifier(token, chat_id, http_post=http)

    with pytest.raises(TelegramDeliveryError) as caught:
        notifier.deliver(_reminder())

    assert token not in str(caught.value)
    assert chat_id not in str(caught.value)
