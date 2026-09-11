# Operations and troubleshooting

## Retry policy

The service records every delivery attempt in its SQLite ledger. Network errors,
timeouts, and Telegram HTTP `408`, `425`, `429`, and `5xx` responses are
transient: the reminder remains eligible on the next service loop. A Telegram
`4xx` response other than those transient statuses is permanent, for example an
invalid token or unavailable chat. It is retained in the ledger for diagnosis
but is not retried automatically.

Official-source retrieval is source-local and persists its retry state beside
the source cache. A BLS `403` or `404` therefore cannot cause one request per
service loop, including after a container restart or before the first calendar
was successfully downloaded. The other official sources continue normally.

| Failure | Retry policy | Cached-calendar fallback |
| --- | --- | --- |
| `403`, `404`, other permanent `4xx`, invalid content | `source_rejection_cooldown_minutes` | Only while younger than `source_max_stale_cache_hours`. |
| Timeout, network error, `408`, `425`, `429`, `5xx` | Exponential from `source_poll_interval_minutes`, capped by `source_retry_max_backoff_minutes` | Only while younger than `source_max_stale_cache_hours`. |
| Valid HTTP `Retry-After` | Never earlier than the supplied time | Same limit. |

A successful `200` or `304` clears the cooldown. A fallback cache does not
refresh its retrieval or validation time. Defaults are a six-hour rejection
cooldown, one-day maximum temporary backoff, and seven-day maximum fallback
cache age. These values are deliberately conservative for public institutional
sites; lower them only when the provider explicitly permits more frequent
access.

## Safe diagnostics

For cache-only inspection and an explicit bounded live probe, see
[source diagnostics](source-diagnostics.md). The command does not send messages
or update the delivery ledger. The continuous service now includes HTTP status,
failure category, cache age, validation time, and future coverage in its source
logs. Stale cached data is reported as degraded and does not refresh health.

The continuous CLI writes structured human-readable logs to standard error.
They contain source names, event counts, delivery outcome, HTTP/error codes, and
whether a failure is retryable. They never contain a Telegram token, chat ID,
Telegram request URL, notification body, or exception message supplied by an
external service.

For Docker Compose, inspect recent operational facts with:

```bash
docker compose logs --tail=100 macro-event-telegram-alerts
docker compose ps
```

## Troubleshooting

| Symptom | Safe check | Likely action |
| --- | --- | --- |
| `Configuration error` | Run `check-config` against the local TOML file. | Compare local files with the tracked examples; keep values in `.env`. |
| Source failure in logs | Note the safe source name, HTTP/error type, cache age, and `next_request_at`. | Keep the cache volume, wait for the recorded cooldown, then check the institution's public schedule. |
| Telegram HTTP 401/403/400 | Confirm the token and chat ID locally without printing them. | Correct the local `.env`, then restart; permanent failures are not automatically retried. |
| Container is unhealthy | Run `docker compose ps` and inspect safe logs. | Verify source access and delivery configuration; do not remove the volume unless a deliberate reset is required. |
| A test notification is needed | Use `dry-run` first. | It prints due messages without reading Telegram credentials or contacting Telegram. |

To intentionally clear all cache and delivery history, stop the service and run
`docker compose down --volumes`. This also removes deduplication history and can
cause otherwise eligible reminders to be sent again.
