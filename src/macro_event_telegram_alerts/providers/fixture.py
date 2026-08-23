"""Deterministic JSON fixture provider for offline tests and demonstrations."""

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from json import JSONDecodeError
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance, SignificancePolicy

type Clock = Callable[[], datetime]
type JsonObject = Mapping[str, object]


class FixtureError(ValueError):
    """A JSON fixture does not satisfy the documented event contract."""


class JsonFixtureProvider:
    """Load normalized events from JSON using an injected clock."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def load(self, path: Path) -> tuple[MacroEvent, ...]:
        """Load events from a UTF-8 JSON fixture file."""
        return self.loads(path.read_text(encoding="utf-8"))

    def loads(self, payload: str) -> tuple[MacroEvent, ...]:
        """Load events from JSON text without network access."""
        try:
            document: object = json.loads(payload)
        except JSONDecodeError as error:
            raise FixtureError(f"fixture is not valid JSON: {error.msg}") from error

        root = _mapping(document, "fixture root")
        raw_events = _sequence(_required(root, "events"), "events")
        retrieved_at = self._retrieved_at()

        return tuple(
            self._parse_event(_mapping(item, f"events[{index}]"), retrieved_at)
            for index, item in enumerate(raw_events)
        )

    def _retrieved_at(self) -> datetime:
        retrieved_at = self._clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise FixtureError("fixture clock must return a timezone-aware datetime")
        if retrieved_at.utcoffset() != UTC.utcoffset(retrieved_at):
            raise FixtureError("fixture clock must return UTC")
        return retrieved_at

    def _parse_event(
        self,
        raw: JsonObject,
        retrieved_at: datetime,
    ) -> MacroEvent:
        timing_precision = _enum_value(
            TimingPrecision,
            _string(_required(raw, "timing_precision"), "timing_precision"),
            "timing_precision",
        )
        scheduled_date = _date_value(
            _string(_required(raw, "scheduled_date"), "scheduled_date")
        )
        starts_at_local, starts_at_utc = _event_times(raw)
        policy = _policy(_mapping(_required(raw, "policy"), "policy"))

        try:
            return MacroEvent(
                source_id=_string(_required(raw, "source_id"), "source_id"),
                title=_string(_required(raw, "title"), "title"),
                institution=_string(
                    _required(raw, "institution"),
                    "institution",
                ),
                source_url=_string(_required(raw, "source_url"), "source_url"),
                scheduled_date=scheduled_date,
                timing_precision=timing_precision,
                policy=policy,
                retrieved_at=retrieved_at,
                starts_at_local=starts_at_local,
                starts_at_utc=starts_at_utc,
            )
        except ValueError as error:
            raise FixtureError(str(error)) from error


def _event_times(raw: JsonObject) -> tuple[datetime | None, datetime | None]:
    value = raw.get("starts_at")
    if value is None:
        return None, None

    timestamp = _string(value, "starts_at")
    timezone_name = _string(
        _required(raw, "source_timezone"),
        "source_timezone",
    )
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise FixtureError("starts_at must be an ISO 8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FixtureError("starts_at must include an explicit UTC offset")

    try:
        source_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise FixtureError(f"unknown source_timezone: {timezone_name}") from error

    source_local = parsed.astimezone(source_timezone)
    if source_local.replace(tzinfo=None) != parsed.replace(tzinfo=None):
        raise FixtureError("starts_at offset does not match source_timezone")
    return source_local, source_local.astimezone(UTC)


def _policy(raw: JsonObject) -> SignificancePolicy:
    significance = _enum_value(
        EventSignificance,
        _string(_required(raw, "significance"), "policy.significance"),
        "policy.significance",
    )
    revision = _string(_required(raw, "revision"), "policy.revision")
    try:
        return SignificancePolicy(significance=significance, revision=revision)
    except ValueError as error:
        raise FixtureError(str(error)) from error


def _required(raw: JsonObject, name: str) -> object:
    try:
        return raw[name]
    except KeyError as error:
        raise FixtureError(f"missing required field: {name}") from error


def _mapping(value: object, field_name: str) -> JsonObject:
    if not isinstance(value, Mapping):
        raise FixtureError(f"{field_name} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise FixtureError(f"{field_name} keys must be strings")
    return value


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise FixtureError(f"{field_name} must be an array")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise FixtureError(f"{field_name} must be a string")
    return value


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise FixtureError("scheduled_date must be an ISO 8601 date") from error


def _enum_value[EnumType: (EventSignificance, TimingPrecision)](
    enum_type: type[EnumType],
    value: str,
    field_name: str,
) -> EnumType:
    try:
        return enum_type(value)
    except ValueError as error:
        raise FixtureError(f"unsupported {field_name}: {value}") from error
