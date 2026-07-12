"""Groq Qwen3-32B text adapter using Groq's official chat endpoint."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.exceptions import ProviderResponseError
from app.providers.base import (
    ProviderHealth,
    TextGenerationRequest,
    TextGenerationResponse,
)
from app.providers.http import HttpTransport, post_json


class GroqTextProvider:
    """Generate schema-bound text through Groq's Qwen3-32B model."""

    name = "groq_qwen3_32b"
    priority = 1
    model = "qwen/qwen3-32b"
    _endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, *, transport: HttpTransport | None = None) -> None:
        """Create the adapter with runtime configuration and optional test transport."""

        self._api_key = api_key
        self._transport = transport

    def health_check(self) -> ProviderHealth:
        """Report configured readiness without making a billable network request."""

        return ProviderHealth(
            available=bool(self._api_key),
            checked_at=datetime.now(UTC),
            reason=None if self._api_key else "GROQ_API_KEY is not configured.",
        )

    def generate_json(self, request: TextGenerationRequest) -> TextGenerationResponse:
        """Request strict JSON output using Groq's documented schema format."""

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "reasoning_effort": "none",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "shorts_content",
                    "strict": True,
                    "schema": request.schema,
                },
            },
        }
        response = post_json(
            self._endpoint,
            {"Authorization": f"Bearer {self._api_key}"},
            payload,
            transport=self._transport,
        )
        return TextGenerationResponse(
            content=_openai_content(response),
            model=self.model,
        )


def _openai_content(response: dict[str, object]) -> dict[str, object]:
    """Extract and parse the OpenAI-compatible chat-completion content field."""

    try:
        choices = response["choices"]
        message = choices[0]["message"]  # type: ignore[index]
        content = message["content"]  # type: ignore[index]
        parsed = json.loads(content)
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
