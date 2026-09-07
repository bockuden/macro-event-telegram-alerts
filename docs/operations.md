# Operations and troubleshooting

## Retry policy

The service records every delivery attempt in its SQLite ledger. Network errors,
timeouts, and Telegram HTTP `408`, `425`, `429`, and `5xx` responses are
transient: the reminder remains eligible on the next service loop. A Telegram
`4xx` response other than those transient statuses is permanent, for example an
invalid token or unavailable chat. It is retained in the ledger for diagnosis
but is not retried automatically.

Official-source retrieval follows the same conservative distinction. A cached
official document can be reused on a network failure, rate limit, or server
failure; malformed data, an unexpected content type, and other permanent HTTP
responses fail the source instead of masking a source-contract change.

## Safe diagnostics

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
| Source failure in logs | Note only the safe source name and error type. | Keep the cache volume, wait for the next loop, then check the institution's public schedule. |
| Telegram HTTP 401/403/400 | Confirm the token and chat ID locally without printing them. | Correct the local `.env`, then restart; permanent failures are not automatically retried. |
| Container is unhealthy | Run `docker compose ps` and inspect safe logs. | Verify source access and delivery configuration; do not remove the volume unless a deliberate reset is required. |
| A test notification is needed | Use `dry-run` first. | It prints due messages without reading Telegram credentials or contacting Telegram. |

To intentionally clear all cache and delivery history, stop the service and run
`docker compose down --volumes`. This also removes deduplication history and can
cause otherwise eligible reminders to be sent again.
