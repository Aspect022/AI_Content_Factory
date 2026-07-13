"""Groq Llama 3.1 8B text adapter using Groq's official chat endpoint."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    Groq,
    RateLimitError,
)

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


class GroqTextProvider:
    """Generate schema-bound text through Groq's free-tier Llama 3.3 70B model."""

    name = "groq_llama_3_3_70b"
    priority = 1
    model = "llama-3.3-70b-versatile"

    def __init__(self, api_key: str, *, transport: HttpTransport | None = None) -> None:
        """Create the adapter with runtime configuration and optional test transport."""

        self._api_key = api_key
        self._transport = transport
        if not self._transport and api_key:
            import httpx

            # Use a pre-configured HTTPX client passed to Groq SDK
            http_client = httpx.Client(
                timeout=httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
            self._client = Groq(api_key=api_key, http_client=http_client)
        else:
            self._client = None
        self._endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def health_check(self) -> ProviderHealth:
        """Report configured readiness without making a billable network request."""

        return ProviderHealth(
            available=bool(self._api_key),
            checked_at=datetime.now(UTC),
            reason=None if self._api_key else "GROQ_API_KEY is not configured.",
        )

    def generate_json(self, request: TextGenerationRequest) -> TextGenerationResponse:
        """Request strict JSON output using Groq's documented schema format."""

        prompt = (
            f"{request.prompt}\n"
            f"Return only one valid JSON object matching this schema:\n"
            f"{json.dumps(request.schema)}"
        )

        if self._transport:
            # Test mode fallback using the transport
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
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

        import time

        start_time = time.monotonic()
        try:
            chat_completion = self._client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                response_format={"type": "json_object"},
            )
            duration = time.monotonic() - start_time
            import sys

            sys.stderr.write(f"Request to Groq completed in {duration:.2f}s\n")
            sys.stderr.flush()

            content = chat_completion.choices[0].message.content
            parsed = clean_and_parse_json(content)
            return TextGenerationResponse(content=parsed, model=self.model)

        except json.JSONDecodeError as error:
            raise ProviderResponseError.from_message(
                code="invalid_provider_json",
                message="The provider response was not valid JSON.",
                retriable=True,
                failure_step="text_generation",
            ) from error
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ProviderResponseError.from_message(
                code="invalid_provider_response",
                message="The provider response did not contain a JSON completion.",
                retriable=True,
                failure_step="text_generation",
            ) from error
        except RateLimitError as error:
            raise QuotaExceededError.from_message(
                code="provider_quota_exhausted",
                message="The provider reported no available quota.",
                retriable=True,
                failure_step="text_generation",
            ) from error
        except APIStatusError as error:
            status_code = error.status_code
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
        except APITimeoutError as error:
            duration = time.monotonic() - start_time
            import sys

            sys.stderr.write(f"Request to Groq timed out after {duration:.2f}s\n")
            sys.stderr.flush()
            import httpx

            # Preserve original exception style logic
            raise httpx.TimeoutException("The read operation timed out") from error
        except APIConnectionError as error:
            raise ProviderUnavailableError.from_message(
                code="provider_network_error",
                message="The provider could not be reached.",
                retriable=True,
                failure_step="text_generation",
            ) from error


def _openai_content(response: dict[str, object]) -> dict[str, object]:
    """Extract and parse the OpenAI-compatible chat-completion content field."""

    try:
        choices = response["choices"]
        message = choices[0]["message"]  # type: ignore[index]
        content = message["content"]  # type: ignore[index]
        parsed = clean_and_parse_json(content)
    except (IndexError, KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
        raise ProviderResponseError.from_message(
            code="invalid_provider_response",
            message="The provider response did not contain a JSON completion.",
            retriable=True,
            failure_step="text_generation",
        ) from error
    return parsed
