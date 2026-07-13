"""Small injectable HTTP transport used by concrete provider adapters."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.exceptions import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderResponseError,
    ProviderUnavailableError,
    QuotaExceededError,
)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A provider HTTP response normalized for injectable test transports."""

    status_code: int
    body: str


HttpTransport = Callable[[str, Mapping[str, str], dict[str, object]], HttpResponse]


def post_json(
    url: str,
    headers: Mapping[str, str],
    payload: dict[str, object],
    *,
    transport: HttpTransport | None = None,
) -> dict[str, object]:
    """POST JSON through the injected or standard-library transport."""

    response = (transport or _standard_transport)(url, headers, payload)
    if response.status_code >= 400:
        import sys

        # Log final request URL and response body on failure (excluding
        # confidential headers/payload)
        sys.stderr.write(
            json.dumps(
                {
                    "event": "http_request_failed",
                    "url": url,
                    "status_code": response.status_code,
                    "response_body": response.body,
                }
            )
            + "\n"
        )
        sys.stderr.flush()
        _raise_for_status(response.status_code, response.body)
    try:
        decoded = json.loads(response.body)
    except json.JSONDecodeError as error:
        raise ProviderResponseError.from_message(
            code="invalid_provider_json",
            message="The provider response was not valid JSON.",
            retriable=True,
            failure_step="text_generation",
        ) from error
    if not isinstance(decoded, dict):
        raise ProviderResponseError.from_message(
            code="invalid_provider_response",
            message="The provider response must be a JSON object.",
            retriable=True,
            failure_step="text_generation",
        )
    return decoded


def _standard_transport(
    url: str, headers: Mapping[str, str], payload: dict[str, object]
) -> HttpResponse:
    req_headers = {"Content-Type": "application/json", **headers}
    if "generativelanguage.googleapis.com" not in url:
        req_headers["User-Agent"] = "curl/8.5.0"

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=req_headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310
            return HttpResponse(response.status, response.read().decode("utf-8"))
    except HTTPError as error:
        return HttpResponse(error.code, error.read().decode("utf-8", errors="replace"))
    except (TimeoutError, URLError) as error:
        raise ProviderUnavailableError.from_message(
            code="provider_network_error",
            message="The provider could not be reached.",
            retriable=True,
            failure_step="text_generation",
        ) from error


def _raise_for_status(status_code: int, body: str = "") -> None:
    """Raise a typed, secret-safe error for a provider HTTP status."""

    if _is_credential_rejection(body):
        raise ProviderAuthenticationError.from_message(
            code="provider_authentication_failed",
            message="The provider rejected its configured credentials.",
            retriable=False,
            failure_step="text_generation",
        )
    if status_code == 429:
        raise QuotaExceededError.from_message(
            code="provider_quota_exhausted",
            message="The provider reported no available quota.",
            retriable=False,
            failure_step="text_generation",
        )
    if status_code in {401, 403}:
        raise ProviderAuthenticationError.from_message(
            code="provider_authentication_failed",
            message="The provider rejected its configured credentials.",
            retriable=False,
            failure_step="text_generation",
        )
    if status_code >= 500:
        raise ProviderUnavailableError.from_message(
            code="provider_server_error",
            message="The provider returned a transient server error.",
            retriable=True,
            failure_step="text_generation",
        )
    raise ProviderError.from_message(
        code="provider_request_failed",
        message=(
            "The provider rejected the text generation request "
            f"(HTTP {status_code})."
        ),
        retriable=False,
        failure_step="text_generation",
    )


def _is_credential_rejection(body: str) -> bool:
    """Classify common 400-level credential failures without logging provider text."""

    try:
        payload = json.loads(body)
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        message = error.get("message", "") if isinstance(error, dict) else ""
    except json.JSONDecodeError:
        return False
    if not isinstance(message, str):
        return False
    normalized = message.lower()
    return "api key" in normalized or "credential" in normalized


def clean_and_parse_json(content: str) -> dict[str, object]:
    """Extract and parse the JSON object, removing thinking blocks."""

    import re

    # Remove any reasoning/thinking blocks
    cleaned = re.sub(r"(?s)<think>.*?</think>", "", content)
    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>", 1)[0]

    # Find the first { and last }
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_str = cleaned[start_idx : end_idx + 1]
    else:
        json_str = cleaned

    parsed = json.loads(json_str)
    if not isinstance(parsed, dict):
        raise ValueError("Parsed JSON must be a dictionary object.")
    return parsed
