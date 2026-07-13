"""Gemini 2.5 Flash text adapter using the official GenerateContent REST API."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.exceptions import ProviderResponseError
from app.providers.base import (
    ProviderHealth,
    TextGenerationRequest,
    TextGenerationResponse,
)
from app.providers.groq_provider import _parse_json_object
from app.providers.http import HttpTransport, post_json


class GeminiTextProvider:
    """Generate schema-bound text through Gemini 2.5 Flash."""

    name = "gemini_2_5_flash"
    priority = 3
    model = "gemini-2.5-flash"
    _endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )

    def __init__(self, api_key: str, *, transport: HttpTransport | None = None) -> None:
        """Create the adapter with runtime configuration and optional test transport."""

        self._api_key = api_key
        self._transport = transport

    def health_check(self) -> ProviderHealth:
        """Report configured readiness without making a remote request."""

        return ProviderHealth(
            available=bool(self._api_key),
            checked_at=datetime.now(UTC),
            reason=None if self._api_key else "GEMINI_API_KEY is not configured.",
        )

    def generate_json(self, request: TextGenerationRequest) -> TextGenerationResponse:
        """Request structured JSON using Gemini's documented generation config."""

        response = post_json(
            self._endpoint,
            {"x-goog-api-key": self._api_key},
            {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": f"{request.prompt}\n"
                                "Return only one valid JSON object."
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                },
            },
            transport=self._transport,
        )
        return TextGenerationResponse(
            content=_gemini_content(response), model=self.model
        )


def _gemini_content(response: dict[str, object]) -> dict[str, object]:
    """Extract and parse the first text part from a GenerateContent response."""

    try:
        candidates = response["candidates"]
        content = candidates[0]["content"]  # type: ignore[index]
        parts = content["parts"]  # type: ignore[index]
        text = parts[0]["text"]  # type: ignore[index]
        parsed = _parse_json_object(text)
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ProviderResponseError.from_message(
            code="invalid_provider_response",
            message="The provider response did not contain a JSON completion.",
            retriable=True,
            failure_step="text_generation",
        ) from error
    if not isinstance(parsed, dict):
        raise ProviderResponseError.from_message(
            code="invalid_provider_response",
            message="The provider completion must be a JSON object.",
            retriable=True,
            failure_step="text_generation",
        )
    return parsed
