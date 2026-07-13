"""Gemini 1.5 Flash text adapter using the official SDK."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from google import genai
from google.genai.errors import APIError

from app.exceptions import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderResponseError,
    ProviderUnavailableError,
    QuotaExceededError,
)
from app.providers.base import (
    ProviderHealth,
    TextGenerationRequest,
    TextGenerationResponse,
)
from app.providers.http import (
    HttpTransport,
    clean_and_parse_json,
    post_json,
)


class GeminiTextProvider:
    """Generate schema-bound text through Gemini 1.5 Flash."""

    name = "gemini_1_5_flash"
    priority = 3
    model = "gemini-1.5-flash"

    def __init__(self, api_key: str, *, transport: HttpTransport | None = None) -> None:
        """Create the adapter with runtime configuration and optional test transport."""

        self._api_key = api_key
        self._transport = transport
        if not self._transport and api_key:
            # We configure the genai client using http_options
            # It maps to httpx client options under the hood
            self._client = genai.Client(
                api_key=api_key, http_options={"timeout": 180.0}
            )
        else:
            self._client = None
        self._endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-1.5-flash:generateContent"
        )

    def health_check(self) -> ProviderHealth:
        """Report configured readiness without making a remote request."""

        return ProviderHealth(
            available=bool(self._api_key),
            checked_at=datetime.now(UTC),
            reason=None if self._api_key else "GEMINI_API_KEY is not configured.",
        )

    def generate_json(self, request: TextGenerationRequest) -> TextGenerationResponse:
        """Request structured JSON using Gemini's documented generation config."""

        prompt = (
            f"{request.prompt}\n"
            f"Return only one valid JSON object matching this schema:\n"
            f"{json.dumps(request.schema)}"
        )

        if self._transport:
            response = post_json(
                self._endpoint,
                {"x-goog-api-key": self._api_key},
                {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                    },
                },
                transport=self._transport,
            )
            return TextGenerationResponse(
                content=_gemini_content(response), model=self.model
            )

        import time

        start_time = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            duration = time.monotonic() - start_time
            import sys

            sys.stderr.write(f"Request to Gemini completed in {duration:.2f}s\n")
            sys.stderr.flush()

            parsed = clean_and_parse_json(response.text)
            return TextGenerationResponse(content=parsed, model=self.model)

        except json.JSONDecodeError as error:
            raise ProviderResponseError.from_message(
                code="invalid_provider_json",
                message="The provider response was not valid JSON.",
                retriable=True,
                failure_step="text_generation",
            ) from error
        except ValueError as error:
            raise ProviderResponseError.from_message(
                code="invalid_provider_response",
                message="The provider response did not contain a JSON completion.",
                retriable=True,
                failure_step="text_generation",
            ) from error
        except APIError as error:
            status_code = error.code
            if status_code == 429:
                raise QuotaExceededError.from_message(
                    code="provider_quota_exhausted",
                    message="The provider reported no available quota.",
                    retriable=True,
                    failure_step="text_generation",
                ) from error
            if status_code in {401, 403}:
                raise ProviderAuthenticationError.from_message(
                    code="provider_authentication_failed",
                    message="The provider rejected its configured credentials.",
                    retriable=False,
                    failure_step="text_generation",
                ) from error
            if status_code >= 500:
                raise ProviderUnavailableError.from_message(
                    code="provider_server_error",
                    message="The provider returned a transient server error.",
                    retriable=True,
                    failure_step="text_generation",
                ) from error
            raise ProviderError.from_message(
                code="provider_request_failed",
                message=(
                    "The provider rejected the text generation request "
                    f"(HTTP {status_code})."
                ),
                retriable=False,
                failure_step="text_generation",
            ) from error
        except Exception as error:
            import httpx

            if isinstance(error, httpx.TimeoutException) or (
                hasattr(error, "__cause__")
                and isinstance(error.__cause__, httpx.TimeoutException)
            ):
                duration = time.monotonic() - start_time
                import sys

                sys.stderr.write(f"Request to Gemini timed out after {duration:.2f}s\n")
                sys.stderr.flush()
                if isinstance(error, httpx.TimeoutException):
                    raise
                else:
                    raise error.__cause__ from None  # type: ignore
            if isinstance(error, httpx.RequestError) or (
                hasattr(error, "__cause__")
                and isinstance(error.__cause__, httpx.RequestError)
            ):
                raise ProviderUnavailableError.from_message(
                    code="provider_network_error",
                    message="The provider could not be reached.",
                    retriable=True,
                    failure_step="text_generation",
                ) from error
            raise


def _gemini_content(response: dict[str, object]) -> dict[str, object]:
    """Extract and parse the first text part from a GenerateContent response."""

    try:
        candidates = response["candidates"]
        content = candidates[0]["content"]  # type: ignore[index]
        parts = content["parts"]  # type: ignore[index]
        text = parts[0]["text"]  # type: ignore[index]
        parsed = clean_and_parse_json(text)
    except (IndexError, KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
        raise ProviderResponseError.from_message(
            code="invalid_provider_response",
            message="The provider response did not contain a JSON completion.",
            retriable=True,
            failure_step="text_generation",
        ) from error
    return parsed
