"""Telegram Bot API notifier with no secret-bearing log output."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.exceptions import NotificationError
from app.providers.base import NotificationRequest, ProviderHealth


class TelegramNotificationProvider:
    """Send pipeline success and failure messages through Telegram's Bot API."""

    name = "telegram_bot_api"
    priority = 1

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            available=bool(self._bot_token and self._chat_id),
            checked_at=datetime.now(UTC),
            reason=(
                None
                if self._bot_token and self._chat_id
                else "Telegram is not configured."
            ),
        )

    def send(self, request: NotificationRequest) -> None:
        if not self.health_check().available:
            raise NotificationError.from_message(
                code="telegram_not_configured",
                message="Telegram credentials are not configured.",
                retriable=False,
                failure_step="notification",
            )
        body = json.dumps({"chat_id": self._chat_id, "text": request.message}).encode(
            "utf-8"
        )
        endpoint = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        try:
            with urlopen(  # noqa: S310
                Request(
                    endpoint, data=body, headers={"Content-Type": "application/json"}
                ),
                timeout=30,
            ) as response:
                if response.status >= 400:
                    raise NotificationError.from_message(
                        code="telegram_send_failed",
                        message="Telegram rejected the notification.",
                        retriable=response.status >= 500,
                        failure_step="notification",
                    )
        except (HTTPError, URLError, TimeoutError) as error:
            raise NotificationError.from_message(
                code="telegram_send_failed",
                message="Telegram could not deliver the notification.",
                retriable=True,
                failure_step="notification",
            ) from error
