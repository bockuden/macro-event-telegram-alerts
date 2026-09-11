# Source diagnostics

This command is introduced after v0.1.0. It is not available inside the original
v0.1.0 image; use a build containing Issue #13 or a subsequent released image.

## Inspect the existing cache without network access

```bash
python -m macro_event_telegram_alerts diagnose-sources --config config.toml
```

Use the installed environment's Python. For a running updated Compose service:

```bash
docker compose -f compose.release.yaml exec macro-event-telegram-alerts \
  python -m macro_event_telegram_alerts diagnose-sources --config /app/config.toml
```

The default `cache-only` mode reads calendar files and their metadata. It makes
no HTTP requests, reads no `.env` or token file, creates no Telegram notifier,
and neither opens nor updates the delivery ledger or health file. It does not
write the source cache. A missing cache is reported as `cache_missing`, not as
an empty successful calendar. Cache-only inspection cannot confirm current
network access or reconstruct a previous HTTP error that was not persisted.

## Explicitly allow source retrieval

```bash
python -m macro_event_telegram_alerts diagnose-sources --live --config config.toml
```

`--live` allows the same fixed official URLs, request timeout, response-size
limit, conditional HTTP validation, and polling/cache rules as normal source
loading. It does not force a request when the cache is still fresh or an
existing retry deadline has not arrived. It may update source cache files;
delivery state, health state, and Telegram remain untouched.

Avoid running a live diagnostic process concurrently with a service sharing
the same cache. On an updated Compose deployment, pause the service and run
one diagnostic process, then restart it even if diagnostics returns exit 1:

```bash
docker compose -f compose.release.yaml stop macro-event-telegram-alerts
docker compose -f compose.release.yaml run --rm --no-deps macro-event-telegram-alerts \
  diagnose-sources --live --config /app/config.toml
docker compose -f compose.release.yaml up -d
```

No command here deletes the state volume. Pausing can delay reminders, so use
cache-only inspection first. This issue adds visibility, not a new retry policy:
without a valid cache, repeated live invocations can still repeat a rejected
request. Persistent cooldowns for this case are tracked in Issue #14; fallback
BLS coverage is tracked in Issue #15. Do not loop this command against a 403.

## Interpret the JSON report

Every configured source has its own report; a failure does not hide the others.

| Field | Meaning |
| --- | --- |
| `status` | `healthy`: parsed usable cache/fetch; `degraded`: stale cache or retrieval failure with usable cached data; `failed`: no usable source events were loaded |
| `category` | `http`, `timeout`, `network`, `content`, `cache`, `cache_missing`, `parse`, or `unknown`; `null` when no failure category was observed |
| `http_status` | HTTP status observed by this attempt, such as `403`; `null` if no HTTP response was observed |
| `retrieved_at` | Time the cached document body was retrieved, in UTC |
| `validated_at` | Last successful HTTP 200/304 validation, not a failed request's time |
| `cache_age_seconds` | Age of the document body, which can stay old after a successful 304 validation |
| `next_request_at` | Earliest request time permitted by existing cache/poll metadata; not a guarantee that a request will succeed |
| `from_cache`, `stale` | Whether cached data was used and whether successful validation is overdue or unknown |
| `total_events` | All selected parsed events, including historical and date-only events |
| `future_events` | Future timed events and date-only events dated today or later (UTC date comparison) |
| `future_timed_events` | Future events with an exact or tentative UTC instant that can enter reminder scheduling |
| `next_event_at` | Earliest such future instant in UTC; `null` if none is available |

Counts are `null` after a load failure; a successfully parsed empty calendar has
zero counts. `healthy` with zero future events means parsing succeeded, not that
coverage is sufficient or that Telegram delivery has been verified. The report
does not include raw response bodies, exception messages, bot tokens, chat IDs,
or notification content. Share this report rather than `.env`, a full Docker
inspection, or a rendered Compose configuration that may contain secrets.

Exit codes: `0` when all sources are healthy, `1` if any source is degraded or
failed, and `2` for invalid configuration/arguments. JSON is written to stdout.

Old cache metadata remains readable. If it records a deferred retry but no
separate successful-validation time, `validated_at` is unknown (`null`). It is
not inferred from a failed check. A later successful request records the time.

## Continuous service logs and health

The service emits the same safe fields in `Official source status` log lines,
including `source=bls category=http http_status=403` on a BLS HTTP rejection
(other fields may appear between them). It continues processing healthy sources.
Serving stale fallback cache is reported as degraded and does not refresh the
successful-loop health timestamp. After the freshness window expires, Docker
can therefore report `unhealthy` even while the process is running.

These diagnostics do not repair blocked BLS access, verify Telegram delivery,
or provide outage notifications. Those are separate recovery-plan tasks.
