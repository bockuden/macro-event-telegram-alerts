# BEA release-schedule adapter

The BEA adapter ingests scheduled national GDP and Personal Income and Outlays
releases from the U.S. Bureau of Economic Analysis. It needs no API key and does
not collect release values, market forecasts, or third-party impact scores.

## Source boundary

The only live input is the official full BEA release schedule:

`https://www.bea.gov/news/schedule/full`

The URL is a code constant, not operator configuration. This prevents the BEA
adapter from silently switching to a mirror or aggregate calendar. A row's
release link is retained when present and must resolve to HTTPS on `bea.gov`.
BEA commonly leaves future rows without a detail link; those events retain the
official full schedule URL until a release page is published.

The adapter treats schedule times as Eastern Time (`America/New_York`). This
matches BEA's published convention that news releases are posted at Eastern
time unless otherwise noted. The timezone database determines EST or EDT for
each date, and the normalized event also stores UTC. Missing, invalid,
nonexistent, or ambiguous times fail visibly instead of being guessed.

References:

- [Current BEA full release schedule](https://www.bea.gov/news/schedule/full)
- [BEA schedule publication convention](https://apps.bea.gov/scb/issues/2023/12-december/1223-news-releases-2024.htm)

## Reviewed aliases

Matching uses case-folded, whitespace-normalized prefixes with an explicit
separator boundary. Fuzzy matching is not used.

| Normalized family | Accepted schedule prefixes |
| --- | --- |
| Gross Domestic Product (GDP) | `GDP (Advance Estimate)`, `GDP (Second Estimate)`, `GDP (Third Estimate)`, `GDP (Updated Estimate)`, `Gross Domestic Product,` |
| Personal Income and Outlays (PCE) | `Personal Income and Outlays,` |

Only rows marked by BEA's schedule layout as News releases are eligible. This
excludes similarly named state, county, territorial, data-only, visual-data,
and article entries. The adapter also requires both reviewed families to occur
in a full schedule; if a layout or naming change removes a family, ingestion
fails rather than returning an incomplete set silently.

Both families receive project policy revision
`bea-significant-releases-v1`. “Significant” is this project's classification,
not a rating supplied by BEA.

## Layout-drift contract

The parser validates the HTML structure observed on August 30, 2026:

- exactly one table with ID `release-schedule-table`;
- exactly one `Year YYYY` header;
- typed schedule rows inside the table body;
- a `release-date` field and a `release-title` field in every row;
- at most one source link per row;
- a displayed time for every selected GDP or PCE release.

Changing the table ID, row-type class, title class, year header, or selected-row
time causes an explicit parser error. The parser does not fall back to scraping
arbitrary page text.

## Retrieval and cache policy

The schedule changes infrequently, but rescheduling can occur. The transport:

- requires a `User-Agent` containing an HTTP(S) or `mailto:` contact;
- makes at most one validation request per six hours by default;
- persists the HTML document and retrieval metadata;
- sends `If-None-Match` and `If-Modified-Since` when validators are available;
- limits requests to 20 seconds and responses to 4 MiB;
- reuses a stale cache after network errors, rate limiting, and server errors;
- rejects unexpected content types and non-UTF-8 responses.

Six hours is a conservative project default, not a polling interval specified
by BEA. Operators may poll less often but should not disable caching or use
aggressive retrieval.

## Attribution and commercial review

BEA says that, unless otherwise stated, information on its site is public domain
and may be used without specific permission; it appreciates attribution such as
“Source: U.S. Bureau of Economic Analysis.” Every normalized event therefore
retains the institution and an official source URL.

BEA also says that links must not imply agency endorsement of a commercial
product and restricts use of its logo beyond link identification. Before adding
subscriptions, advertising, or a hosted commercial service, recheck current BEA
policies and review the final presentation for attribution and non-endorsement.

References:

- [BEA copyright FAQ](https://www.bea.gov/help/faq/147)
- [BEA linking and attribution policy](https://www.bea.gov/about/policies-and-information/linking)

## Offline contract tests

`tests/fixtures/bea-schedule-minimal.html` is a hand-minimized recording of the
official schedule structure and selected 2026 rows reviewed on August 30, 2026.
It includes published links, future rows without links, EDT and EST dates,
regional lookalikes, and a non-News lookalike. It is not a complete BEA page or
historical archive.

HTTP behavior uses an injected in-memory client. CI never contacts BEA, so page
availability cannot make builds flaky.
