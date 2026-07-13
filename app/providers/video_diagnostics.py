"""Secret-safe structured diagnostics shared by video provider adapters."""

from __future__ import annotations

import json
import logging
from time import monotonic
from urllib.parse import urlsplit, urlunsplit


def request_started() -> float:
    """Return a monotonic request start marker for durable diagnostics."""

    return monotonic()


def log_http_failure(
    *,
    provider: str,
    model: str,
    endpoint: str,
    status_code: int,
    response_body: bytes,
    started_at: float,
    polling_status: str | None = None,
    job_id: str | None = None,
    download_url: str | None = None,
) -> None:
    """Emit error context without leaking credentials or signed URL queries."""

    logging.getLogger("ai_shorts_factory.video").error(
        json.dumps(
            {
                "event": "video_provider_http_failure",
                "provider": provider,
                "model": model,
                "endpoint": _safe_url(endpoint),
                "http_status": status_code,
                "response_body": _safe_body(response_body),
                "request_duration_seconds": round(monotonic() - started_at, 3),
                "polling_status": polling_status,
                "job_id": job_id,
                "download_url": (
                    None if download_url is None else _safe_url(download_url)
                ),
            },
            sort_keys=True,
        )
    )


def _safe_url(url: str) -> str:
    """Drop query strings because they can contain API keys or signed tokens."""

    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _safe_body(body: bytes) -> str:
    """Limit and redact an API error response before durable logging."""

    text = body.decode("utf-8", errors="replace")[:2_000]
    for marker in ("api_key", "apiKey", "authorization", "token", "secret"):
        text = text.replace(marker, "[redacted-field]")
    return text
