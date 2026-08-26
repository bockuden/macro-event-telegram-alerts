"""Respectful, cached transport for the official BLS iCalendar feed."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BLS_CALENDAR_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
DEFAULT_MIN_POLL_INTERVAL = timedelta(hours=6)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class BlsTransportError(RuntimeError):
    """The official BLS calendar could not be retrieved or cached safely."""


@dataclass(frozen=True, slots=True)
class HttpResult:
    """Small HTTP result type used to keep transport tests offline."""

    status: int
    body: bytes
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class BlsCalendarPayload:
    """Calendar text plus provenance about when it was retrieved."""

    text: str
    retrieved_at: datetime
    from_cache: bool


type Clock = Callable[[], datetime]
type HttpGet = Callable[[str, Mapping[str, str], float], HttpResult]


@dataclass(frozen=True, slots=True)
class _CacheMetadata:
    checked_at: datetime
    retrieved_at: datetime
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class _CachedCalendar:
    text: str
    metadata: _CacheMetadata


class BlsCalendarTransport:
    """Fetch only the official BLS ICS feed with conditional requests."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        user_agent: str,
        clock: Clock,
        min_poll_interval: timedelta = DEFAULT_MIN_POLL_INTERVAL,
        timeout_seconds: float = 20.0,
        http_get: HttpGet | None = None,
    ) -> None:
        if not _has_contact(user_agent):
            raise ValueError("user_agent must include an HTTP(S) or mailto contact")
        if min_poll_interval <= timedelta(0):
            raise ValueError("min_poll_interval must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._cache_dir = cache_dir
        self._user_agent = user_agent
        self._clock = clock
        self._min_poll_interval = min_poll_interval
        self._timeout_seconds = timeout_seconds
        self._http_get = http_get or _urllib_get

    def fetch(self) -> BlsCalendarPayload:
        """Return a fresh or conditionally validated official calendar."""
        now = _utc_time(self._clock(), "clock")
        cached = self._read_cache()
        if cached is not None:
            age = now - cached.metadata.checked_at
            if timedelta(0) <= age < self._min_poll_interval:
                return _payload_from_cache(cached)

        headers = {
            "Accept": "text/calendar",
            "User-Agent": self._user_agent,
        }
        if cached is not None and cached.metadata.etag:
            headers["If-None-Match"] = cached.metadata.etag
        if cached is not None and cached.metadata.last_modified:
            headers["If-Modified-Since"] = cached.metadata.last_modified

        try:
            result = self._http_get(
                BLS_CALENDAR_URL,
                headers,
                self._timeout_seconds,
            )
        except (OSError, URLError) as error:
            if cached is not None:
                return _payload_from_cache(cached)
            raise BlsTransportError("BLS calendar request failed") from error

        if result.status == 304:
            if cached is None:
                raise BlsTransportError("BLS returned 304 without a local cache")
            metadata = _CacheMetadata(
                checked_at=now,
                retrieved_at=cached.metadata.retrieved_at,
                etag=_header(result.headers, "etag") or cached.metadata.etag,
                last_modified=(
                    _header(result.headers, "last-modified")
                    or cached.metadata.last_modified
                ),
            )
            self._write_cache(cached.text, metadata)
            return BlsCalendarPayload(
                text=cached.text,
                retrieved_at=metadata.retrieved_at,
                from_cache=True,
            )

        if result.status != 200:
            if cached is not None and result.status >= 500:
                return _payload_from_cache(cached)
            raise BlsTransportError(f"BLS calendar returned HTTP {result.status}")

        content_type = _header(result.headers, "content-type")
        if content_type is None or "text/calendar" not in content_type.lower():
            raise BlsTransportError("BLS calendar returned an unexpected content type")
        if len(result.body) > MAX_RESPONSE_BYTES:
            raise BlsTransportError("BLS calendar response exceeds the size limit")
        try:
            text = result.body.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise BlsTransportError("BLS calendar is not valid UTF-8") from error
        text = _normalize_newlines(text)

        metadata = _CacheMetadata(
            checked_at=now,
            retrieved_at=now,
            etag=_header(result.headers, "etag"),
            last_modified=_header(result.headers, "last-modified"),
        )
        self._write_cache(text, metadata)
        return BlsCalendarPayload(text=text, retrieved_at=now, from_cache=False)

    def _read_cache(self) -> _CachedCalendar | None:
        calendar_path = self._cache_dir / "bls.ics"
        metadata_path = self._cache_dir / "bls-cache.json"
        if not calendar_path.exists() and not metadata_path.exists():
            return None
        if not calendar_path.is_file() or not metadata_path.is_file():
            raise BlsTransportError("BLS cache is incomplete")

        try:
            raw_metadata: object = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata = _parse_metadata(raw_metadata)
            text = calendar_path.read_text(encoding="utf-8-sig")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise BlsTransportError("BLS cache is invalid") from error
        return _CachedCalendar(text=text, metadata=metadata)

    def _write_cache(self, text: str, metadata: _CacheMetadata) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        calendar_path = self._cache_dir / "bls.ics"
        metadata_path = self._cache_dir / "bls-cache.json"
        calendar_tmp = self._cache_dir / "bls.ics.tmp"
        metadata_tmp = self._cache_dir / "bls-cache.json.tmp"

        metadata_document = {
            "checked_at": metadata.checked_at.isoformat(),
            "retrieved_at": metadata.retrieved_at.isoformat(),
            "etag": metadata.etag,
            "last_modified": metadata.last_modified,
        }
        try:
            calendar_tmp.write_text(text, encoding="utf-8", newline="\n")
            metadata_tmp.write_text(
                json.dumps(metadata_document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            calendar_tmp.replace(calendar_path)
            metadata_tmp.replace(metadata_path)
        except OSError as error:
            raise BlsTransportError("BLS cache could not be written") from error


def _urllib_get(
    url: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> HttpResult:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            return HttpResult(
                status=response.status,
                body=body,
                headers=dict(response.headers.items()),
            )
    except HTTPError as error:
        return HttpResult(
            status=error.code,
            body=error.read(MAX_RESPONSE_BYTES + 1),
            headers=dict(error.headers.items()) if error.headers else {},
        )


def _parse_metadata(value: object) -> _CacheMetadata:
    if not isinstance(value, dict):
        raise ValueError("cache metadata must be an object")
    checked_at = _metadata_datetime(value, "checked_at")
    retrieved_at = _metadata_datetime(value, "retrieved_at")
    return _CacheMetadata(
        checked_at=checked_at,
        retrieved_at=retrieved_at,
        etag=_optional_string(value.get("etag"), "etag"),
        last_modified=_optional_string(
            value.get("last_modified"),
            "last_modified",
        ),
    )


def _metadata_datetime(value: dict[object, object], name: str) -> datetime:
    raw = value.get(name)
    if not isinstance(raw, str):
        raise ValueError(f"cache {name} must be a string")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(f"cache {name} must be ISO 8601") from error
    return _utc_time(parsed, f"cache {name}")


def _optional_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"cache {name} must be a string or null")
    return value


def _utc_time(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use UTC")
    return value.astimezone(UTC)


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    return next(
        (value for key, value in headers.items() if key.lower() == lowered),
        None,
    )


def _payload_from_cache(cached: _CachedCalendar) -> BlsCalendarPayload:
    return BlsCalendarPayload(
        text=cached.text,
        retrieved_at=cached.metadata.retrieved_at,
        from_cache=True,
    )


def _has_contact(user_agent: str) -> bool:
    lowered = user_agent.lower()
    return any(marker in lowered for marker in ("https://", "http://", "mailto:"))


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")
