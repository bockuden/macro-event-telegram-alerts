# BLS iCalendar adapter

The first live-source adapter ingests a narrow, reviewed subset of the U.S.
Bureau of Labor Statistics release calendar. It needs no API key and does not
collect actual values, forecasts, or third-party importance scores.

## Source boundary

The only live input is the official BLS iCalendar feed:

`https://www.bls.gov/schedule/news_release/bls.ics`

The URL is a code constant rather than runtime configuration. This prevents an
operator from silently pointing the BLS adapter at a mirror or third-party
calendar. Event links are accepted only when they use HTTPS on `bls.gov`; if an
event omits its URL, the adapter uses the reviewed official release page for
that event family.

BLS says its release-calendar times are Eastern Time. A floating iCalendar
`DATE-TIME` is therefore interpreted as `America/New_York`, with daylight-saving
rules supplied by the Python timezone database. Explicit UTC and
`America/New_York` timestamps are also accepted. Unknown timezones, nonexistent
or ambiguous local times, duplicate UIDs, and malformed selected events fail
visibly. A `VALUE=DATE` event remains date-only and is not assigned an invented
time.

References:

- [BLS calendar](https://www.bls.gov/schedule/news_release/)
- [BLS iCalendar help](https://www.bls.gov/help/hlpiCAL.htm)
- [RFC 5545: iCalendar](https://www.rfc-editor.org/rfc/rfc5545)

## Reviewed event aliases

Aliases are matched after case-folding and whitespace normalization, but only
as complete names. Substring and fuzzy matching are intentionally excluded.

| Normalized family | Accepted BLS summary aliases |
| --- | --- |
| Consumer Price Index | `Consumer Price Index` |
| Employment Situation | `Employment Situation` |
| Producer Price Index | `Producer Price Index`, `Producer Price Indexes` |
| Job Openings and Labor Turnover Survey | `Job Openings and Labor Turnover Survey`, `Job Openings and Labor Turnover` |

All four families receive the project policy revision
`bls-significant-releases-v1`. “Significant” is this project's classification,
not a BLS rating. Any other BLS release is ignored until its alias and product
scope receive an explicit review.

## Respectful retrieval and cache policy

BLS prohibits excessive automated retrieval and may block robots that send
multiple requests per second or do not provide owner contact information. The
transport therefore:

- requires a `User-Agent` containing an HTTP(S) or `mailto:` contact;
- makes at most one validation request per six hours by default;
- stores the calendar and cache metadata locally;
- sends `If-None-Match` and `If-Modified-Since` when BLS supplies validators;
- limits requests to 20 seconds and responses to 2 MiB;
- reuses a stale cache after a network error or BLS 5xx response;
- rejects unexpected content types and non-UTF-8 payloads.

Six hours is a conservative project default, not a frequency promised or
required by BLS. The BLS help page says the weekly calendar is updated on Friday
afternoons and may be updated when scheduling information changes. A deployment
may poll less frequently, but must not disable caching or use aggressive polling.

References:

- [BLS terms of service](https://www.bls.gov/bls/blsterms.htm)
- [BLS copyright and attribution](https://www.bls.gov/opub/copyright-information.htm)

## Attribution and commercial review

BLS describes most of its published information as public domain, subject to
noted exceptions, and asks that BLS be cited. Every normalized event therefore
retains the institution and an official source URL. User-facing notifications
must display that attribution.

This implementation is not a legal conclusion about every future use. Before a
hosted subscription, advertising product, or public release, recheck the current
BLS policies and verify that the retrieval pattern and presentation still comply.

## Offline contract tests

`tests/fixtures/bls-minimal.ics` is a deliberately minimized contract fixture
derived from the official schedule's published field semantics and reviewed
release names. It is not a historical archive or a verbatim copy of a complete
BLS calendar. It exercises Eastern, floating, UTC, date-only, folded-line, URL
fallback, alias, and ignored-release behavior.

All HTTP behavior is tested with an injected in-memory client. CI never contacts
BLS, so source availability and bot protection cannot make builds flaky.
