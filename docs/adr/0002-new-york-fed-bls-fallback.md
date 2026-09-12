# ADR 0002: Use the New York Fed calendar as the BLS fallback

**Status:** Accepted for implementation on 2026-09-12

## Context

The primary BLS iCalendar endpoint returned HTTP 403 from the production
network. The official BLS HTML release schedule was also denied from the local
automation network with the project's identifying User-Agent, so changing only
the BLS path would not provide independent availability.

The [Federal Reserve Bank of New York economic indicators calendar][nyfed]
lists the required BLS release families, dates, and Eastern Time release times.
It links to the underlying publisher where available and labels the schedule as
tentative and subject to change. It is a public HTML calendar, requires neither
an API key nor a paid account, and is a distinct domain from `bls.gov`.

## Decision

Use the New York Fed monthly calendar as the secondary schedule source only
when the BLS iCalendar source cannot provide a usable calendar. The first
implementation will support these exact labels:

| Logical BLS family | New York Fed label |
| --- | --- |
| Consumer Price Index | `Consumer Price Index` |
| Producer Price Index | `Producer Price Index (PPI)` |
| Employment Situation | `Employment Situation` |
| Job Openings and Labor Turnover Survey | `JOLTS` |

The calendar's times are Eastern Time. The adapter must retain that timezone,
apply IANA daylight-saving rules, and must not invent a time if the source does
not display one. Events retain their BLS attribution and official BLS release
page as the event link; diagnostics identify the active schedule as
`new_york_fed` rather than presenting it as a BLS response.

The adapter may poll no more frequently than the configured source interval,
must cache each monthly page independently, and must respect the existing
cooldown/backoff policy. A primary recovery replaces fallback data only after a
successful BLS fetch. Conflicting future event times are a visible degraded
state; they must not silently overwrite an already scheduled reminder.

## Evidence

| Check | Result |
| --- | --- |
| Local request, 2026-09-12 | `https://www.newyorkfed.org/research/calendars/i-sep26.html` returned HTTP 200 with `text/html; charset=utf-8`. |
| Affected production server, 2026-09-12 | The same URL and identifying User-Agent returned HTTP 200 with `text/html; charset=utf-8`. |
| Required coverage | The September 2026 calendar lists JOLTS, Employment Situation, PPI, and CPI with exact Eastern times. |
| Trading Economics | Rejected: its documented API requires a subscription and API key. |

## Consequences

This is not a claim that New York Fed provides a machine-readable API or a
commercial redistribution licence. The project retrieves only the public page,
attributes BLS release events to BLS, and retains the existing operational and
commercial-review safeguards. Before a hosted subscription or advertising
product, recheck the current New York Fed terms and the retrieval pattern.

Implementation remains incomplete until the parser, failover, source identity,
conflict handling, and production diagnostic check described in Issue #15 are
tested and merged.

[nyfed]: https://www.newyorkfed.org/research/calendars/i-sep26.html
