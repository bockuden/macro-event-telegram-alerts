"""Credential-free reminder rendering and local dry-run delivery."""

from collections.abc import Callable

from macro_event_telegram_alerts.domain import TimingPrecision
from macro_event_telegram_alerts.reminders import Reminder

type MessageSink = Callable[[str], None]


class DryRunNotifier:
    """Inspect reminders locally without a bot token or recipient identifier."""

    def __init__(self, sink: MessageSink) -> None:
        self._sink = sink

    def deliver(self, reminder: Reminder) -> None:
        """Render and write one reminder to the configured local sink."""
        self._sink(format_reminder_message(reminder))


def format_reminder_message(reminder: Reminder) -> str:
    """Render source facts without presenting project policy as an official rating."""
    event = reminder.event
    assert event.starts_at_local is not None
    timezone_name = getattr(event.starts_at_local.tzinfo, "key", None)
    timezone_suffix = f" ({timezone_name})" if timezone_name else ""
    local_time = event.starts_at_local.strftime("%Y-%m-%d %H:%M %Z")
    return "\n".join(
        (
            (
                "Macro event reminder — "
                f"{_format_lead_time(reminder.lead_seconds)} remaining"
            ),
            f"Event: {event.title}",
            f"Institution: {event.institution}",
            f"Scheduled local time: {local_time}{timezone_suffix}",
            f"Timing quality: {_timing_quality(event.timing_precision)}",
            f"Source: {event.source_url}",
            (
                "Significance: selected by this project's policy "
                f"({event.policy.significance.value}); "
                "not an official institution rating."
            ),
        )
    )


def _format_lead_time(lead_seconds: int) -> str:
    if lead_seconds % 3600 == 0:
        hours = lead_seconds // 3600
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    if lead_seconds % 60 == 0:
        minutes = lead_seconds // 60
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    return f"{lead_seconds} seconds"


def _timing_quality(precision: TimingPrecision) -> str:
    descriptions = {
        TimingPrecision.EXACT: "exact time published by the source",
        TimingPrecision.TENTATIVE: "tentative time based on the source schedule",
        TimingPrecision.DATE_ONLY: "source published a date but no time",
        TimingPrecision.TBA: "source has not published a time",
    }
    return descriptions[precision]
