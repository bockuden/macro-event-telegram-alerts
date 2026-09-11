"""Shared conditional HTTP cache for infrequently changing official documents."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from enum import StrEnum
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_HTTP_READ_BYTES = 4 * 1024 * 1024


class FailureCategory(StrEnum):
    """Allowlisted diagnostic categories, never external response text."""

    HTTP = "http"
    TIMEOUT = "timeout"
    NETWORK = "network"
    CONTENT = "content"
    CACHE = "cache"
    CACHE_MISSING = "cache_missing"
    PARSE = "parse"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TransportDiagnostics:
    """Safe retrieval facts; unknown values remain None."""

    category: FailureCategory | None = None
    http_status: int | None = None
    retrieved_at: datetime | None = None
    validated_at: datetime | None = None
    next_request_at: datetime | None = None
    from_cache: bool = False
    stale: bool = False


class CachedDocumentError(RuntimeError):
    """An official document could not be retrieved or cached safely."""

    def __init__(
        self,
        message: str,
        *,
        category: FailureCategory = FailureCategory.UNKNOWN,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.http_status = http_status


@dataclass(frozen=True, slots=True)
class HttpResult:
    """Small HTTP result type that allows completely offline transport tests."""

    status: int
    body: bytes
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class CachedDocumentPayload:
    """Decoded document plus retrieval provenance."""

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
    retry_not_before: datetime | None = None
    validated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class _CachedDocument:
    text: str
    metadata: _CacheMetadata


class CachedDocumentTransport:
    """Retrieve one fixed official URL using conditional requests and a cache."""

    def __init__(
        self,
        *,
        source_name: str,
        url: str,
        cache_dir: Path,
        document_filename: str,
        metadata_filename: str,
        user_agent: str,
        clock: Clock,
        accept: str,
        expected_content_type: str,
        min_poll_interval: timedelta,
        max_response_bytes: int,
        timeout_seconds: float = 20.0,
        http_get: HttpGet | None = None,
        allow_network: bool = True,
    ) -> None:
        if not source_name.strip():
            raise ValueError("source_name must not be empty")
        if not _has_contact(user_agent):
            raise ValueError("user_agent must include an HTTP(S) or mailto contact")
        if min_poll_interval <= timedelta(0):
            raise ValueError("min_poll_interval must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 0 < max_response_bytes <= MAX_HTTP_READ_BYTES:
            raise ValueError("max_response_bytes is outside the supported range")

        self._source_name = source_name
        self._url = url
        self._cache_dir = cache_dir
        self._document_filename = document_filename
        self._metadata_filename = metadata_filename
        self._user_agent = user_agent
        self._clock = clock
        self._accept = accept
        self._expected_content_type = expected_content_type
        self._min_poll_interval = min_poll_interval
        self._max_response_bytes = max_response_bytes
        self._timeout_seconds = timeout_seconds
        self._http_get = http_get or _urllib_get
        self._allow_network = allow_network
        self._diagnostics = TransportDiagnostics()

    def diagnostics(self) -> TransportDiagnostics:
        """Return facts from the most recent fetch attempt without I/O."""
        return self._diagnostics

    def fetch(self) -> CachedDocumentPayload:
        """Return a fresh, conditionally validated, or stale cached document."""
        now = _utc_time(self._clock(), "clock")
        self._diagnostics = TransportDiagnostics()
        cached = self._read_cache()
        if cached is not None:
            self._observe_cache(cached, now)
        if not self._allow_network:
            if cached is None:
                raise self._error("has no local cache", FailureCategory.CACHE_MISSING)
            return _payload_from_cache(cached)
        if cached is not None:
            retry_not_before = cached.metadata.retry_not_before
            if retry_not_before is not None and now < retry_not_before:
                return _payload_from_cache(cached)
            age = now - cached.metadata.checked_at
            if timedelta(0) <= age < self._min_poll_interval:
                return _payload_from_cache(cached)

        headers = {"Accept": self._accept, "User-Agent": self._user_agent}
        if cached is not None and cached.metadata.etag:
            headers["If-None-Match"] = cached.metadata.etag
        if cached is not None and cached.metadata.last_modified:
            headers["If-Modified-Since"] = cached.metadata.last_modified

        try:
            result = self._http_get(self._url, headers, self._timeout_seconds)
        except (OSError, URLError) as error:
            category = (
                FailureCategory.TIMEOUT
                if isinstance(error, TimeoutError)
                or isinstance(getattr(error, "reason", None), TimeoutError)
                else FailureCategory.NETWORK
            )
            self._diagnostics = replace(self._diagnostics, category=category)
            if cached is not None:
                self._defer_retry(cached, now, None)
                return _payload_from_cache(cached)
            raise self._error("request failed", category) from error

        self._diagnostics = replace(self._diagnostics, http_status=result.status)

        if result.status == 304:
            if cached is None:
                raise self._error("returned 304 without a local cache")
            metadata = _CacheMetadata(
                checked_at=now,
                retrieved_at=cached.metadata.retrieved_at,
                etag=_header(result.headers, "etag") or cached.metadata.etag,
                last_modified=(
                    _header(result.headers, "last-modified")
                    or cached.metadata.last_modified
                ),
                retry_not_before=None,
                validated_at=now,
            )
            self._write_cache(cached.text, metadata)
            self._observe_cache(_CachedDocument(cached.text, metadata), now)
            return CachedDocumentPayload(
                text=cached.text,
                retrieved_at=metadata.retrieved_at,
                from_cache=True,
            )

        if result.status != 200:
            self._diagnostics = replace(
                self._diagnostics, category=FailureCategory.HTTP
            )
            if cached is not None and _is_transient_status(result.status):
                self._defer_retry(cached, now, result.headers)
                return _payload_from_cache(cached)
            raise self._error(f"returned HTTP {result.status}", FailureCategory.HTTP)

        content_type = _header(result.headers, "content-type")
        if (
            content_type is None
            or self._expected_content_type not in content_type.lower()
        ):
            raise self._error(
                "returned an unexpected content type", FailureCategory.CONTENT
            )
        if len(result.body) > self._max_response_bytes:
            raise self._error(
                "response exceeds the size limit", FailureCategory.CONTENT
            )
        try:
            text = result.body.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise self._error(
                "response is not valid UTF-8", FailureCategory.CONTENT
            ) from error

        text = _normalize_newlines(text)
        metadata = _CacheMetadata(
            checked_at=now,
            retrieved_at=now,
            etag=_header(result.headers, "etag"),
            last_modified=_header(result.headers, "last-modified"),
            retry_not_before=None,
            validated_at=now,
        )
        self._write_cache(text, metadata)
        self._observe_cache(_CachedDocument(text, metadata), now)
        self._diagnostics = replace(self._diagnostics, from_cache=False)
        return CachedDocumentPayload(text=text, retrieved_at=now, from_cache=False)

    def _observe_cache(self, cached: _CachedDocument, now: datetime) -> None:
        metadata = cached.metadata
        validated = metadata.validated_at
        next_request = metadata.checked_at + self._min_poll_interval
        if metadata.retry_not_before is not None:
            next_request = max(next_request, metadata.retry_not_before)
        self._diagnostics = replace(
            self._diagnostics,
            retrieved_at=metadata.retrieved_at,
            validated_at=validated,
            next_request_at=next_request,
            from_cache=True,
            stale=(validated is None or now >= validated + self._min_poll_interval),
        )

    def _defer_retry(
        self,
        cached: _CachedDocument,
        now: datetime,
        headers: Mapping[str, str] | None,
    ) -> None:
        retry_not_before = now + self._min_poll_interval
        if headers is not None:
            retry_after = _retry_after(headers, now)
            if retry_after is not None:
                retry_not_before = max(retry_not_before, retry_after)
        metadata = _CacheMetadata(
            checked_at=now,
            retrieved_at=cached.metadata.retrieved_at,
            etag=cached.metadata.etag,
            last_modified=cached.metadata.last_modified,
            retry_not_before=retry_not_before,
            validated_at=cached.metadata.validated_at,
        )
        self._write_cache(cached.text, metadata)
        self._observe_cache(_CachedDocument(cached.text, metadata), now)

    def _read_cache(self) -> _CachedDocument | None:
        document_path = self._cache_dir / self._document_filename
        metadata_path = self._cache_dir / self._metadata_filename
        if not document_path.exists() and not metadata_path.exists():
            return None
        if not document_path.is_file() or not metadata_path.is_file():
            raise self._error("cache is incomplete", FailureCategory.CACHE)

        try:
            raw_metadata: object = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata = _parse_metadata(raw_metadata)
            text = document_path.read_text(encoding="utf-8-sig")
        except (OSError, ValueError) as error:
            raise self._error("cache is invalid", FailureCategory.CACHE) from error
        return _CachedDocument(text=text, metadata=metadata)

    def _write_cache(self, text: str, metadata: _CacheMetadata) -> None:
        document_path = self._cache_dir / self._document_filename
        metadata_path = self._cache_dir / self._metadata_filename
        document_tmp = document_path.with_suffix(document_path.suffix + ".tmp")
        metadata_tmp = metadata_path.with_suffix(metadata_path.suffix + ".tmp")

        metadata_document = {
            "checked_at": metadata.checked_at.isoformat(),
            "validated_at": (
                metadata.validated_at.isoformat() if metadata.validated_at else None
            ),
            "retrieved_at": metadata.retrieved_at.isoformat(),
            "etag": metadata.etag,
            "last_modified": metadata.last_modified,
            "retry_not_before": (
                metadata.retry_not_before.isoformat()
                if metadata.retry_not_before is not None
                else None
            ),
        }
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            document_tmp.write_text(text, encoding="utf-8", newline="\n")
            metadata_tmp.write_text(
                json.dumps(metadata_document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            document_tmp.replace(document_path)
            metadata_tmp.replace(metadata_path)
        except OSError as error:
            raise self._error(
                "cache could not be written", FailureCategory.CACHE
            ) from error

    def _error(
        self, message: str, category: FailureCategory = FailureCategory.CONTENT
    ) -> CachedDocumentError:
        self._diagnostics = replace(self._diagnostics, category=category)
        return CachedDocumentError(
            f"{self._source_name} {message}",
            category=category,
            http_status=self._diagnostics.http_status,
        )


def _urllib_get(
    url: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> HttpResult:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(MAX_HTTP_READ_BYTES + 1)
            return HttpResult(
                status=response.status,
                body=body,
                headers=dict(response.headers.items()),
            )
    except HTTPError as error:
        return HttpResult(
            status=error.code,
            body=error.read(MAX_HTTP_READ_BYTES + 1),
            headers=dict(error.headers.items()) if error.headers else {},
        )


def _parse_metadata(value: object) -> _CacheMetadata:
    if not isinstance(value, dict):
        raise ValueError("cache metadata must be an object")
    return _CacheMetadata(
        checked_at=_metadata_datetime(value, "checked_at"),
        retrieved_at=_metadata_datetime(value, "retrieved_at"),
        etag=_optional_string(value.get("etag"), "etag"),
        last_modified=_optional_string(value.get("last_modified"), "last_modified"),
        retry_not_before=_optional_datetime(
            value.get("retry_not_before"), "retry_not_before"
        ),
        validated_at=(
            _optional_datetime(value.get("validated_at"), "validated_at")
            if "validated_at" in value
            else _metadata_datetime(value, "checked_at")
            if value.get("retry_not_before") is None
            else None
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


def _optional_datetime(value: object, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"cache {name} must be a string or null")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"cache {name} must be ISO 8601") from error
    return _utc_time(parsed, f"cache {name}")


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


def _payload_from_cache(cached: _CachedDocument) -> CachedDocumentPayload:
    return CachedDocumentPayload(
        text=cached.text,
        retrieved_at=cached.metadata.retrieved_at,
        from_cache=True,
    )


def _has_contact(user_agent: str) -> bool:
    lowered = user_agent.lower()
    return any(marker in lowered for marker in ("https://", "http://", "mailto:"))


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _is_transient_status(status: int) -> bool:
    return status in {408, 425, 429} or status >= 500


def _retry_after(headers: Mapping[str, str], now: datetime) -> datetime | None:
    value = _header(headers, "retry-after")
    if value is None:
        return None
    try:
        delay_seconds = int(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None or retry_at.utcoffset() is None:
            return None
        return retry_at.astimezone(UTC)
    if delay_seconds < 0:
        return None
    return now + timedelta(seconds=delay_seconds)
