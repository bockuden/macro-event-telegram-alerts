# Scheduled FOMC calendar adapter

The FOMC adapter represents the two scheduled communications that follow every
regular policy meeting: the policy statement and the Chair's press conference.
It does not predict the policy decision or ingest rates, projections, minutes,
speeches, emergency decisions, or unscheduled meetings.

## Official source boundary

Meeting dates and published event links come only from the Federal Reserve
Board's official FOMC calendar:

`https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`

The URL is fixed in code. Event links must use HTTPS on
`federalreserve.gov`. When a future meeting has no statement or press-conference
page yet, the normalized event links to the official calendar instead.

The adapter processes the current calendar year and any future year displayed
on that page. It requires exactly eight unique, chronological regular meetings
for each processed year. Rows explicitly marked `notation vote` or
`unscheduled` are outside the v0.1 scope. Any other unfamiliar date form fails
visibly.

References:

- [FOMC meeting calendars and information](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- [What is the FOMC and when does it meet?](https://www.federalreserve.gov/faqs/about_12844.htm)

## Explicit timing policy

The meeting calendar supplies dates but does not place times in future meeting
rows. Times therefore come from explicit Federal Reserve documentation, not an
HTML guess:

- policy statement: 2:00 p.m. Eastern Time on the second meeting day;
- Chair's press conference: 2:30 p.m. Eastern Time on the same day.

The Federal Reserve's August 9, 2024 announcement states those times alongside
the complete tentative 2025 and 2026 schedules. The Board's current FAQ also
states that a policy statement and press briefing follow each regular meeting.

References:

- [Official 2025–2026 schedule and communication times](https://www.federalreserve.gov/newsevents/pressreleases/monetary20240809a.htm)
- [Federal Reserve announcement of the 2:00/2:30 timing policy](https://www.federalreserve.gov/newsevents/pressreleases/monetary20130313a.htm)

Both timestamps use `America/New_York` and are also stored in UTC. Tests cover
both EST and EDT meetings. Nonexistent or ambiguous Eastern local times fail
instead of being silently adjusted.

## Timing precision and identity

The calendar says meeting dates remain tentative until confirmed at the
preceding meeting. The adapter therefore labels future meeting communications
as `tentative`; communications on concluded meeting dates are `exact`. Both
still carry a precise scheduled instant because the timing policy is explicit.

Each event ID contains the calendar year, the regular meeting's stable ordinal,
and the communication kind. A date reschedule therefore changes the timestamp
without creating a new logical event ID, as long as meeting order is preserved.

Published statement and press-conference links must encode the same decision
date as their calendar row. Missing links for concluded meetings, link-date
mismatches, duplicate links, or non-Federal-Reserve hosts are errors.

## Layout-drift contract

The parser validates the structure reviewed on September 3, 2026:

- headings formatted as `YYYY FOMC Meetings`;
- meeting containers carrying the `fomc-meeting` class;
- one `fomc-meeting__month` and one `fomc-meeting__date` field per row;
- non-empty link targets and link text;
- exactly eight regular rows per current or future year.

If these assumptions change, ingestion stops. It never falls back to searching
arbitrary page prose for month names or numbers.

## Retrieval and cache policy

The shared official-document transport:

- requires a `User-Agent` containing an HTTP(S) or `mailto:` contact;
- makes at most one validation request per six hours by default;
- persists the HTML document and retrieval metadata;
- sends `If-None-Match` and `If-Modified-Since` when available;
- limits requests to 20 seconds and responses to 4 MiB;
- reuses a stale cache after network errors, rate limiting, and server errors;
- rejects unexpected content types and non-UTF-8 responses.

Six hours is a conservative project setting, not a Federal Reserve requirement.
Operators may poll less often but should not disable caching or retrieve the
calendar aggressively.

## Attribution and commercial review

The Board states that its website information is public domain unless otherwise
indicated, asks users to cite the Board as the source, and restricts use of Board
seals and logos. It also disclaims endorsement of commercial products. User
messages must retain the Federal Open Market Committee attribution and official
source URL without suggesting endorsement.

Before adding subscriptions, advertising, or hosted commercial operation,
recheck the current policy and presentation.

Reference: [Federal Reserve Board disclaimer](https://www.federalreserve.gov/disclaimer.htm)

## Offline contract tests

`tests/fixtures/fomc-calendar-minimal.html` is a hand-minimized recording of the
official 2025–2026 calendar structure reviewed on September 3, 2026. It contains
one actual notation-vote shape, all eight 2026 regular meeting rows, historical
event links, projection markers, and future rows without links. It is not a full
page snapshot or historical archive.

HTTP behavior uses an injected in-memory client. CI never contacts the Federal
Reserve website.
