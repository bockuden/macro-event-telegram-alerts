FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --prefix=/install .

FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/bockuden/macro-event-telegram-alerts" \
    org.opencontainers.image.description="Reliable Telegram reminders for significant macroeconomic events." \
    org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=build /install /usr/local
COPY config.example.toml /app/config.example.toml
RUN mkdir /app/state && chown app:app /app/state

USER app

ENTRYPOINT ["python", "-m", "macro_event_telegram_alerts"]
CMD ["run", "--config", "/app/config.toml"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=2m --retries=3 \
    CMD ["python", "-m", "macro_event_telegram_alerts.healthcheck", "/app/state/health.json", "--max-age-seconds", "180"]
