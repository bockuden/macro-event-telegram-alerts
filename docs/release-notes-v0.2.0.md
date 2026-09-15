# Macro Event Telegram Alerts v0.2.0

Recovery release for the BLS source outage observed after v0.1.0.

## Included

- BLS fallback coverage through the public New York Fed economic indicators
  calendar when the primary BLS calendar endpoint is rejected.
- Detailed source diagnostics that preserve HTTP status, active source, retry
  timing, cache freshness, and future-event counts without exposing secrets.
- Persistent source retry cooldowns to avoid hammering rejected endpoints.
- Optional bounded operational Telegram notifications when a source becomes
  degraded or failed, plus one recovery message after it returns to healthy.
- Default reminder lead times of 48 hours, 24 hours, 60 minutes, and
  15 minutes.

## Validation

- On 2026-09-15, live diagnostics reported the FOMC source as healthy with the
  next timed event at `2026-09-16T18:00:00+00:00`, matching the scheduled
  September 15-16, 2026 FOMC meeting.
- The same live diagnostic run reported the primary BLS endpoint as HTTP 403
  and the active BLS source as `new_york_fed`, with future BLS events loaded.
- Offline Ruff, mypy, pytest, container smoke tests, GHCR publication, and
  server upgrade evidence must be recorded before marking the release complete.

## Upgrade Notes

Use `ghcr.io/bockuden/macro-event-telegram-alerts:v0.2.0` with the tracked
`compose.release.yaml`. Preserve the existing Compose volume during upgrade so
the SQLite reminder ledger, source cache, and operational incident state remain
available.

Do not run `docker compose down --volumes` during a normal upgrade. Removing
the volume intentionally resets reminder deduplication and may allow eligible
reminders to be sent again.

## Limitations

- This is a calendar reminder tool, not a trading signal, forecast, actual-data
  feed, or financial-advice service.
- The New York Fed fallback restores selected BLS event timing coverage, but it
  is not a full replacement for every BLS calendar entry.
- Telegram smoke tests must be explicitly labelled as tests; synthetic messages
  must not be presented as real macro events.
