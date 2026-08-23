# Normalized event model

`MacroEvent` is the boundary between institution-specific adapters and reminder
logic. Adapters may parse different formats, but they must produce the same
validated fields.

## Source facts

- `source_id`: stable identifier within an adapter;
- `title` and `institution`: source-owned display information;
- `source_url`: absolute official HTTP(S) URL;
- `scheduled_date`: the date announced by the source;
- `timing_precision`: `exact`, `tentative`, `date_only`, or `tba`;
- `starts_at_local`: aware source-local datetime when an instant is known;
- `starts_at_utc`: the same instant normalized to UTC;
- `retrieved_at`: aware UTC time at which the source document was processed.

Exact and tentative events require both datetime fields. Date-only and TBA
events require neither, so the system never turns an unknown time into midnight.

## Project policy

`SignificancePolicy` is deliberately separate from source facts. It records the
project-assigned `significance` and the configuration `revision` that made the
classification. Messages must not present this value as an institution rating.

## JSON fixture contract

Fixtures have an `events` array. Each event contains the normalized source
fields plus `source_timezone`, an IANA timezone name used to interpret
`starts_at`.

```json
{
  "events": [
    {
      "source_id": "bls:cpi:2026-09-15",
      "title": "Consumer Price Index",
      "institution": "U.S. Bureau of Labor Statistics",
      "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
      "scheduled_date": "2026-09-15",
      "timing_precision": "exact",
      "source_timezone": "America/New_York",
      "starts_at": "2026-09-15T08:30:00-04:00",
      "policy": {
        "significance": "significant",
        "revision": "us-major-events-v1"
      }
    }
  ]
}
```

An explicit offset is recommended. A local wall time without an offset is
accepted only when it identifies one real instant in `source_timezone`.
Ambiguous DST times require an explicit offset, and nonexistent DST times are
rejected. The provider receives a clock from its caller, allowing every fixture
test to control `retrieved_at` without network access or wall-clock sleeps.
