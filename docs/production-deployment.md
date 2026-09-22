# Production deployment and rollback

This is the copy-paste runbook for a Linux server using the public GHCR image.
It keeps the Compose-managed `macro_event_state` volume across upgrades, so
the reminder ledger, source cache, incident state, and health file survive
container recreation.

## 1. Install a pinned release

Install Docker Engine and the Docker Compose plugin, then create a dedicated
directory:

```bash
mkdir -p /opt/macro-event-telegram-alerts
cd /opt/macro-event-telegram-alerts
VERSION=v0.2.1
curl -fsSLO "https://raw.githubusercontent.com/bockuden/macro-event-telegram-alerts/${VERSION}/compose.release.yaml"
curl -fsSLO "https://raw.githubusercontent.com/bockuden/macro-event-telegram-alerts/${VERSION}/config.example.toml"
curl -fsSLO "https://raw.githubusercontent.com/bockuden/macro-event-telegram-alerts/${VERSION}/.env.example"
cp config.example.toml config.toml
cp .env.example .env
chmod 600 .env
```

Edit `.env` locally on the server. Never put these values in Git, the TOML
file, shell history, issue comments, or logs:

```text
MACRO_EVENT_TELEGRAM_BOT_TOKEN=your-BotFather-token
MACRO_EVENT_TELEGRAM_CHAT_ID=your-private-or-group-chat-id
```

The release Compose file is image-pinned and has no build step. Before starting,
verify the image reference and pull it:

```bash
grep 'image:' compose.release.yaml
docker compose -f compose.release.yaml pull
docker image inspect ghcr.io/bockuden/macro-event-telegram-alerts:${VERSION} \
  --format '{{index .RepoDigests 0}}'
```

The digest output is optional evidence for the deployment record. For strict
reproducibility, replace the image tag in `compose.release.yaml` with the
recorded `@sha256:...` digest and keep the tag in your change log.

## 2. Start and verify

```bash
docker compose -f compose.release.yaml up -d
docker compose -f compose.release.yaml ps
docker compose -f compose.release.yaml logs --tail=100 macro-event-telegram-alerts
```

The container health check becomes healthy after a successful loop and a fresh
health file. Run the explicit post-install checks without starting a second
long-running service:

```bash
docker compose -f compose.release.yaml run --rm macro-event-telegram-alerts \
  check-config --config /app/config.toml
docker compose -f compose.release.yaml run --rm macro-event-telegram-alerts \
  send-test --config /app/config.toml
docker compose -f compose.release.yaml run --rm macro-event-telegram-alerts \
  status --config /app/config.toml
docker compose -f compose.release.yaml run --rm macro-event-telegram-alerts \
  diagnose-sources --config /app/config.toml
```

`send-test` contacts Telegram and sends one labelled message. The other
commands are read-only with respect to the reminder ledger. `status` and
`diagnose-sources` may return exit code 1 when a source is degraded; inspect
their output rather than treating that as a container crash.

## 3. Upgrade without losing state

Download the new release Compose file while preserving the local `.env`,
`config.toml`, and named volume:

```bash
cd /opt/macro-event-telegram-alerts
cp compose.release.yaml compose.release.yaml.bak
NEW_VERSION=vNEXT
curl -fsSLO "https://raw.githubusercontent.com/bockuden/macro-event-telegram-alerts/${NEW_VERSION}/compose.release.yaml"
docker compose -f compose.release.yaml pull
docker compose -f compose.release.yaml up -d
docker compose -f compose.release.yaml ps
docker compose -f compose.release.yaml logs --tail=100 macro-event-telegram-alerts
```

`up -d` recreates only the container when the image changes. The
`macro_event_state` volume is intentionally retained, preventing duplicate
reminders after an upgrade. Confirm the image with `docker image inspect` and
run `status`/`diagnose-sources` after the first loop.

## 4. Roll back safely

If the new image is unhealthy or its behavior is not acceptable, restore the
previous Compose file and tag:

```bash
cd /opt/macro-event-telegram-alerts
cp compose.release.yaml.bak compose.release.yaml
docker compose -f compose.release.yaml pull
docker compose -f compose.release.yaml up -d
docker compose -f compose.release.yaml ps
docker compose -f compose.release.yaml logs --tail=100 macro-event-telegram-alerts
```

If no backup exists, download the previous release's
`compose.release.yaml` from its Git tag and repeat the same commands. Do not
run `docker compose down --volumes` during an upgrade or rollback: it deletes
the SQLite delivery ledger and source cache and can cause eligible reminders to
be sent again. Use `down --volumes` only for an intentional, documented reset.

For a failed deployment, preserve the logs, image tag/digest, and the state
volume before changing anything else. The bot token and chat ID are not needed
for this evidence and must not be included in it.
