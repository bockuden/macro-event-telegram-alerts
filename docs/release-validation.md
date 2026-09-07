# v0.1.0 release validation

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
