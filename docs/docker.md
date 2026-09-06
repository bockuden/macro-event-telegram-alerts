# Docker Compose

Docker Compose runs the same application command as a local installation. The
container is unprivileged, has a read-only filesystem, exposes no incoming
ports, and writes only to the named `macro_event_state` volume. That volume
persists the SQLite delivery ledger, official-source cache, and health state
across container recreation.

## First run

Copy the two local-only files, then set both Telegram values in `.env`:

```bash
cp config.example.toml config.toml
cp .env.example .env
```

On Windows PowerShell, use `Copy-Item` instead of `cp`. Configure the local
`.env` as follows:

```text
MACRO_EVENT_TELEGRAM_BOT_TOKEN=your-token-from-BotFather
MACRO_EVENT_TELEGRAM_CHAT_ID=your-personal-or-group-chat-id
```

Both files are ignored by Git and excluded from the Docker build context.

Start the continuous service with one command:

```bash
docker compose up -d --build
```

Inspect it without printing secrets:

```bash
docker compose ps
docker compose logs --tail=100 macro-event-telegram-alerts
```

The health check becomes healthy after a fully successful service loop. A
failed source or delivery leaves the previous health timestamp unchanged, so a
stale health status reflects a real operational problem. The default example
uses a 60-second loop and a 180-second health freshness window.

Stop the service while preserving its delivery state:

```bash
docker compose down
```

To remove the persistent ledger and cache deliberately, run
`docker compose down --volumes`. This resets deduplication history.
