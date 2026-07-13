"""Offline tests for official text-provider request adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from app.exceptions import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderResponseError,
    ProviderUnavailableError,
    QuotaExceededError,
)
from app.providers.base import TextGenerationRequest
from app.providers.gemini_provider import GeminiTextProvider
from app.providers.groq_provider import GroqTextProvider
from app.providers.http import HttpResponse, post_json
from app.providers.nvidia_provider import NvidiaNimTextProvider

REQUEST = TextGenerationRequest(
    prompt="Create a short Hindi topic.",
    schema={"type": "object", "properties": {"topic": {"type": "string"}}},
)
OPENAI_RESPONSE = {"choices": [{"message": {"content": '{"topic": "Sleep"}'}}]}
GEMINI_RESPONSE = {
    "candidates": [{"content": {"parts": [{"text": '{"topic": "Sleep"}'}]}}]
}


@pytest.mark.parametrize(
    ("provider", "response", "expected_endpoint", "expected_model"),
    [
        (
            GroqTextProvider("groq-key"),
            OPENAI_RESPONSE,
            "https://api.groq.com/openai/v1/chat/completions",
            "llama-3.1-8b-instant",
        ),
        (
            NvidiaNimTextProvider("nvidia-key"),
            OPENAI_RESPONSE,
            "https://integrate.api.nvidia.com/v1/chat/completions",
            "deepseek-ai/deepseek-r1",
        ),
        (
            GeminiTextProvider("gemini-key"),
            GEMINI_RESPONSE,
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent",
            "gemini-2.5-flash",
        ),
    ],
)
def test_text_providers_use_their_official_endpoints_and_parse_json(
    provider: GroqTextProvider | NvidiaNimTextProvider | GeminiTextProvider,
    response: dict[str, object],
    expected_endpoint: str,
    expected_model: str,
) -> None:
    """Each adapter constructs its documented payload through an injected transport."""

    captured: dict[str, object] = {}

    def transport(
        url: str, headers: Mapping[str, str], payload: dict[str, object]
    ) -> HttpResponse:
        captured.update(url=url, headers=dict(headers), payload=payload)
        return HttpResponse(200, json.dumps(response))

    provider._transport = transport  # type: ignore[attr-defined]
    result = provider.generate_json(REQUEST)

    assert result.content == {"topic": "Sleep"}
    assert result.model == expected_model
    assert captured["url"] == expected_endpoint
    assert provider.health_check().available is True


def test_groq_and_gemini_use_compatible_json_object_controls() -> None:
    """Provider-independent validation avoids unsupported remote schema subsets."""

    captured: list[dict[str, object]] = []

    def transport(
        _url: str, _headers: Mapping[str, str], payload: dict[str, object]
    ) -> HttpResponse:
        captured.append(payload)
        return HttpResponse(
            200, json.dumps(OPENAI_RESPONSE if len(captured) == 1 else GEMINI_RESPONSE)
        )

    GroqTextProvider("key", transport=transport).generate_json(REQUEST)
    GeminiTextProvider("key", transport=transport).generate_json(REQUEST)

    assert captured[0]["response_format"] == {"type": "json_object"}
    assert "reasoning_effort" not in captured[0]
    assert captured[1]["generationConfig"] == {
        "responseMimeType": "application/json",
    }


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (429, QuotaExceededError),
        (401, ProviderAuthenticationError),
        (500, ProviderUnavailableError),
        (400, ProviderError),
    ],
)
def test_http_transport_classifies_provider_statuses(
    status_code: int, error_type: type[Exception]
) -> None:
    """Quota, authentication, and server responses become typed provider failures."""

    with pytest.raises(error_type):
        post_json(
            "https://mock.example",
            {},
            {},
            transport=lambda *_args: HttpResponse(status_code, "{}"),
        )


def test_http_transport_classifies_400_credential_rejections() -> None:
    """Some provider APIs return invalid-key errors as HTTP 400."""

    with pytest.raises(ProviderAuthenticationError):
        post_json(
            "https://mock.example",
            {},
            {},
            transport=lambda *_args: HttpResponse(
                400, '{"error":{"message":"API key not valid"}}'
            ),
        )


def test_text_provider_rejects_malformed_completion_and_unconfigured_key() -> None:
    """Bad provider payloads are typed errors and empty configuration is unhealthy."""

    provider = GroqTextProvider(
        "",
        transport=lambda *_args: HttpResponse(200, json.dumps({"choices": []})),
    )

    assert provider.health_check().available is False
    with pytest.raises(ProviderResponseError):
        provider.generate_json(REQUEST)


def test_gemini_provider_rejects_a_malformed_completion() -> None:
    """Gemini responses require a JSON text part before they reach the service."""

    provider = GeminiTextProvider(
        "key", transport=lambda *_args: HttpResponse(200, '{"candidates": []}')
    )

    with pytest.raises(ProviderResponseError):
        provider.generate_json(REQUEST)


def test_openai_compatible_providers_parse_json_wrapped_in_reasoning_text() -> None:
    """Groq/NVIDIA adapters can recover the JSON object from mixed content text."""

    wrapped = {
        "choices": [
            {
                "message": {
                    "content": '<think>reasoning</think>\n{"topic":"Sleep"}\nDone.'
                }
            }
        ]
    }
    for provider in (GroqTextProvider("key"), NvidiaNimTextProvider("key")):
        provider._transport = lambda *_args, response=wrapped: HttpResponse(  # type: ignore[attr-defined]
            200, json.dumps(response)
        )
        assert provider.generate_json(REQUEST).content == {"topic": "Sleep"}


def test_gemini_provider_parses_json_fenced_in_markdown() -> None:
    """Gemini adapter can recover a JSON object from fenced markdown text."""

    provider = GeminiTextProvider(
        "key",
        transport=lambda *_args: HttpResponse(
            200,
            json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": '```json\n{"topic":"Sleep"}\n```'}]
                            }
                        }
                    ]
                }
            ),
        ),
    )

    assert provider.generate_json(REQUEST).content == {"topic": "Sleep"}


def test_standard_transport_handles_success_http_errors_and_network_errors() -> None:
    """The standard-library transport is covered without making a real request."""

    class FakeResponse:
        """Minimal URL response context manager for this unit test."""

        status = 200

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"topic": "Sleep"}'

    with patch("app.providers.http.urlopen", return_value=FakeResponse()):
        assert post_json("https://mock.example", {}, {}) == {"topic": "Sleep"}

    http_error = HTTPError("https://mock.example", 429, "quota", None, BytesIO(b"{}"))
    with patch("app.providers.http.urlopen", side_effect=http_error):
        with pytest.raises(QuotaExceededError):
            post_json("https://mock.example", {}, {})

    with patch("app.providers.http.urlopen", side_effect=URLError("offline")):
        with pytest.raises(ProviderUnavailableError):
            post_json("https://mock.example", {}, {})
