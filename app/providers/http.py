"""Small injectable HTTP transport used by concrete provider adapters."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx

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

_CLIENT = httpx.Client(
    timeout=httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
)


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


def print_diagnostics(
    url: str, headers: Mapping[str, str], method: str, error: Exception
) -> None:
    """Print complete Python traceback and underlying request details for debugging."""
    import sys
    import traceback

    sys.stderr.write("=" * 80 + "\n")
    sys.stderr.write("COMPLETE PYTHON TRACEBACK:\n")
    traceback.print_exc(file=sys.stderr)
    sys.stderr.write("-" * 80 + "\n")
    sys.stderr.write(f"UNDERLYING EXCEPTION TYPE: {type(error).__name__}\n")
    sys.stderr.write(f"REQUEST URL: {url}\n")
    sys.stderr.write(f"HTTP METHOD: {method}\n")

    redacted_headers = {}
    for k, v in headers.items():
        k_lower = k.lower()
        if "key" in k_lower or "auth" in k_lower or "token" in k_lower:
            redacted_headers[k] = "[REDACTED]"
        else:
            redacted_headers[k] = v
    sys.stderr.write(f"REQUEST HEADERS: {redacted_headers}\n")

    if isinstance(error, httpx.HTTPStatusError):
        try:
            body = error.response.text
            sys.stderr.write(f"RESPONSE BODY: {body}\n")
        except Exception:
            pass
    sys.stderr.write("=" * 80 + "\n")
    sys.stderr.flush()


def _standard_transport(
    url: str, headers: Mapping[str, str], payload: dict[str, object]
) -> HttpResponse:
    req_headers = {"Content-Type": "application/json", **headers}
    if "generativelanguage.googleapis.com" not in url:
        req_headers["User-Agent"] = "curl/8.5.0"

    import time

    start_time = time.monotonic()

    try:
        response = _CLIENT.post(url, headers=req_headers, json=payload)
        duration = time.monotonic() - start_time
        import sys

        sys.stderr.write(
            f"Request to {url} completed in {duration:.2f}s (status {response.status_code})\n"
        )
        sys.stderr.flush()

        response.raise_for_status()
        return HttpResponse(response.status_code, response.text)
    except httpx.HTTPStatusError as error:
        duration = time.monotonic() - start_time
        import sys

        sys.stderr.write(
            f"Request to {url} failed in {duration:.2f}s (status {error.response.status_code})\n"
        )
        sys.stderr.flush()
        print_diagnostics(url, req_headers, "POST", error)
        return HttpResponse(error.response.status_code, error.response.text)
    except httpx.TimeoutException as error:
        duration = time.monotonic() - start_time
        import sys

        sys.stderr.write(f"Request to {url} timed out after {duration:.2f}s\n")
        sys.stderr.flush()
        print_diagnostics(url, req_headers, "POST", error)
        # Preserve the original exception
        raise
    except httpx.RequestError as error:
        duration = time.monotonic() - start_time
        import sys

        sys.stderr.write(
            f"Request to {url} failed due to network error after {duration:.2f}s\n"
        )
        sys.stderr.flush()
        print_diagnostics(url, req_headers, "POST", error)
        raise ProviderUnavailableError.from_message(
            code="provider_network_error",
            message="The provider could not be reached.",
            retriable=True,
            failure_step="text_generation",
        ) from error
    except Exception as error:
        duration = time.monotonic() - start_time
        import sys

        sys.stderr.write(
            f"Request to {url} failed with unexpected error after {duration:.2f}s\n"
        )
        sys.stderr.flush()
        print_diagnostics(url, req_headers, "POST", error)
        raise


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
            retriable=True,
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
