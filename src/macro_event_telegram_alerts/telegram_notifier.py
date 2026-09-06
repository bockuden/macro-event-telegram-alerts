"""Minimal Telegram Bot API notifier with secret-safe failures."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from macro_event_telegram_alerts.notifications import format_reminder_message
from macro_event_telegram_alerts.reminders import Reminder

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 30.0


class TelegramDeliveryError(RuntimeError):
    """A reminder could not be confirmed as delivered by Telegram."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Small transport response type for deterministic, offline tests."""

    status: int
    body: bytes
    headers: Mapping[str, str]


type HttpPost = Callable[[str, Mapping[str, str], bytes, float], HttpResponse]
type ChatId = int | str


class TelegramNotifier:
    """Send rendered reminders to one configured Telegram chat."""

    def __init__(
        self,
        bot_token: str,
        chat_id: ChatId,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        http_post: HttpPost | None = None,
    ) -> None:
        if not bot_token.strip():
            raise ValueError("bot_token must not be empty")
        if isinstance(chat_id, str) and not chat_id.strip():
            raise ValueError("chat_id must not be empty")
        if not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError(
                f"timeout_seconds must be between 0 and {MAX_TIMEOUT_SECONDS:g}"
            )
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timeout_seconds = timeout_seconds
        self._http_post = http_post or _urllib_post

    def deliver(self, reminder: Reminder) -> None:
        """Send one message or raise a secret-safe delivery error."""
        payload = json.dumps(
            {
                "chat_id": self._chat_id,
                "text": format_reminder_message(reminder),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        }
        try:
            response = self._http_post(
                f"{TELEGRAM_API_BASE_URL}/bot{self._bot_token}/sendMessage",
                headers,
                payload,
                self._timeout_seconds,
            )
        except (OSError, URLError) as error:
            raise TelegramDeliveryError("Telegram request failed") from error
        if response.status != 200:
            raise TelegramDeliveryError(
                f"Telegram returned unexpected HTTP status {response.status}"
            )
        try:
            document: object = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TelegramDeliveryError(
                "Telegram returned an invalid response"
            ) from error
        if not isinstance(document, dict) or document.get("ok") is not True:
            raise TelegramDeliveryError("Telegram did not confirm message delivery")


def _urllib_post(
    url: str,
    headers: Mapping[str, str],
    body: bytes,
    timeout_seconds: float,
) -> HttpResponse:
    request = Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return HttpResponse(
                status=response.status,
                body=response.read(),
                headers=dict(response.headers.items()),
            )
    except HTTPError as error:
        return HttpResponse(
            status=error.code,
            body=error.read(),
            headers=dict(error.headers.items()) if error.headers else {},
        )
