"""Groq Llama 3.1 8B text adapter using Groq's official chat endpoint."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from app.exceptions import ProviderResponseError
from app.providers.base import (
    ProviderHealth,
    TextGenerationRequest,
    TextGenerationResponse,
)
from app.providers.http import HttpTransport, post_json


class GroqTextProvider:
    """Generate schema-bound text through Groq's free-tier Llama 3.1 8B model."""

    name = "groq_llama_3_1_8b"
    priority = 1
    model = "llama-3.1-8b-instant"
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
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{request.prompt}\nReturn only one valid JSON object."
                    ),
                }
            ],
            "response_format": {"type": "json_object"},
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
        parsed = _parse_json_object(content)
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


def _parse_json_object(content: object) -> dict[str, object]:
    """Parse a JSON object from provider text, tolerating common wrappers."""

    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise TypeError("Provider content must be text or a JSON object.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(parsed, dict):
            return parsed
        raise TypeError("Provider completion must decode to a JSON object.")

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, flags=re.DOTALL)
    if fenced is not None:
        fenced_parsed = json.loads(fenced.group(1))
        if isinstance(fenced_parsed, dict):
            return fenced_parsed
        raise TypeError("Fenced completion must decode to a JSON object.")

    first = content.find("{")
    if first < 0:
        raise TypeError("No JSON object found in provider content.")
    depth = 0
    in_string = False
    escaped = False
    for index in range(first, len(content)):
        character = content[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                parsed_fragment = json.loads(content[first : index + 1])
                if isinstance(parsed_fragment, dict):
                    return parsed_fragment
                raise TypeError("JSON fragment must decode to a JSON object.")
    raise TypeError("No complete JSON object found in provider content.")
