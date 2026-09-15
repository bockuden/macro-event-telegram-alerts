# Release Validation

## v0.2.0

Prepared on 2026-09-15 before the proposed `v0.2.0` tag.

### Local Checks

- `ruff check .` passed in the base project directory.
- `ruff format --check .` reported 83 files already formatted.
- `mypy` passed with no issues in 60 source files.
- Full offline pytest passed with `153 passed`.

### Live Source Check

- `diagnose-sources --live` was run against an isolated temporary config and
  state directory, not the production server volume.
- FOMC source status was `healthy` with 22 future timed events and next event
  `2026-09-16T18:00:00+00:00`, matching the scheduled September 15-16, 2026
  FOMC meeting.
- BEA source status was `healthy`.
- BLS primary retrieval still reported HTTP 403, while the active BLS source
  was `new_york_fed` with 4 future timed fallback events.

### Scheduler Dry Run

- `dry-run` against the same isolated config produced two 48-hour FOMC
  reminders for the September 16, 2026 policy statement and Chair press
  conference.
- The dry run did not read Telegram credentials or contact Telegram.
- The command returned exit 1 because BLS was degraded by the primary HTTP 403,
  even though fallback BLS events were available.

### Pending Before Publication

- User approval is required before pushing the branch, creating a pull request,
  merging, tagging `v0.2.0`, or publishing a GHCR image.
- Local Docker smoke testing was not completed on the Windows host because the
  Docker daemon was unavailable. The tag publication workflow must still build
  the image, run container smoke checks, and verify anonymous pull.
- After tag publication, verify the `v0.2.0` image is anonymously pullable and
  its source tag, package version, and image label match.
- Server upgrade verification remains pending until the published image exists.
  Preserve the existing Compose volume during upgrade.

## v0.1.0

Validated on 2026-09-07 before the `v0.1.0` tag.

## Clean-environment checks

- A clean Docker build installed the package from the tagged source using only
  the declared project metadata.
- The image ran as the unprivileged `app` user and completed
  `check-config --config /app/config.example.toml` without network access or
  credentials.
- Ruff, formatting, mypy, and the full offline pytest suite passed locally.

## Live delivery check

- A single explicitly labelled Telegram delivery test was accepted by the
  Telegram Bot API using local-only credentials before this release.
- No token or chat ID was recorded in this document, Git history, terminal
  output, or example configuration.

## Release workflow check

Pushing the `v0.1.0` source tag triggers the release workflow. It repeats the
quality checks, builds a pre-publish image smoke test, publishes the same tag
as `ghcr.io/bockuden/macro-event-telegram-alerts:v0.1.0`, and verifies an
anonymous pull of that published image.
