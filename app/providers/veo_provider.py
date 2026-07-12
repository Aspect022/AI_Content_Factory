"""Official Gemini API adapter for single-clip Veo 3.1 Fast generation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.exceptions import ProviderResponseError, ProviderUnavailableError
from app.providers.base import ProviderHealth, VideoGenerationRequest, VideoJob


@dataclass(frozen=True, slots=True)
class VideoHttpResponse:
    """Normalized binary response for injected Veo transport tests."""

    status_code: int
    body: bytes


VideoTransport = Callable[
    [str, str, Mapping[str, str], bytes | None], VideoHttpResponse
]


class VeoVideoProvider:
    """Generate one 4, 6, or 8-second portrait clip with Veo 3.1 Fast."""

    name = "veo_3_1_fast"
    priority = 1
    model = "veo-3.1-fast-generate-preview"
    _base_url = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self, api_key: str, *, transport: VideoTransport | None = None
    ) -> None:
        """Create the adapter with a Gemini API key and optional test transport."""

        self._api_key = api_key
        self._transport = transport or _standard_transport

    def health_check(self) -> ProviderHealth:
        """Report key readiness without consuming quota through a network probe."""

        return ProviderHealth(
            available=bool(self._api_key),
            checked_at=datetime.now(UTC),
            reason=None if self._api_key else "GEMINI_API_KEY is not configured.",
        )

    def can_accept(self, request: VideoGenerationRequest) -> bool:
        """Accept one portrait clip using Veo's supported 4, 6, or 8-second lengths."""

        return (
            self.health_check().available
            and request.aspect_ratio == "9:16"
            and request.duration_seconds in {4, 6, 8}
        )

    def create_job(self, request: VideoGenerationRequest) -> VideoJob:
        """Submit one documented Veo long-running generation operation."""

        if not self.can_accept(request):
            raise ProviderUnavailableError.from_message(
                code="video_request_not_accepted",
                message="Veo 3.1 Fast requires a 9:16 clip of 4, 6, or 8 seconds.",
                retriable=False,
                failure_step="video_generation",
            )
        response = self._request_json(
            "POST",
            f"/models/{self.model}:predictLongRunning",
            {
                "instances": [{"prompt": request.prompt}],
                "parameters": {
                    "aspectRatio": request.aspect_ratio,
                    "durationSeconds": str(request.duration_seconds),
                },
            },
        )
        name = response.get("name")
        if not isinstance(name, str) or not name:
            raise ProviderResponseError.from_message(
                code="invalid_video_operation",
                message="Veo did not return a video operation name.",
                retriable=True,
                failure_step="video_generation",
            )
        return VideoJob(job_id=name, status="submitted", model=self.model)

    def poll_job(self, job_id: str) -> VideoJob:
        """Fetch the current documented long-running operation state."""

        response = self._request_json("GET", f"/{job_id}", None)
        if response.get("done") is True:
            if "error" in response:
                raise ProviderUnavailableError.from_message(
                    code="video_generation_failed",
                    message="Veo completed the operation with an error.",
                    retriable=False,
                    failure_step="video_generation",
                )
            return VideoJob(job_id=job_id, status="completed", model=self.model)
        return VideoJob(job_id=job_id, status="running", model=self.model)

    def download_result(self, job_id: str, target_path: Path) -> Path:
        """Download a completed Veo result using its API-key protected URI."""

        operation = self._request_json("GET", f"/{job_id}", None)
        try:
            uri = operation["response"]["generateVideoResponse"]["generatedSamples"][0][
                "video"
            ]["uri"]
        except (IndexError, KeyError, TypeError) as error:
            raise ProviderResponseError.from_message(
                code="video_result_missing",
                message="Veo did not return a downloadable generated video.",
                retriable=True,
                failure_step="video_download",
            ) from error
        if not isinstance(uri, str):
            raise ProviderResponseError.from_message(
                code="video_result_missing",
                message="Veo returned an invalid generated video URI.",
                retriable=True,
                failure_step="video_download",
            )
        response = self._transport("GET", uri, self._headers(), None)
        _require_success(response)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(response.body)
        return target_path

    def _request_json(
        self, method: str, path: str, payload: dict[str, object] | None
    ) -> dict[str, object]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        response = self._transport(
            method, f"{self._base_url}{path}", self._headers(), body
        )
        _require_success(response)
        try:
            decoded = json.loads(response.body)
        except json.JSONDecodeError as error:
            raise ProviderResponseError.from_message(
                code="invalid_video_response",
                message="Veo returned invalid JSON.",
                retriable=True,
                failure_step="video_generation",
            ) from error
        if not isinstance(decoded, dict):
            raise ProviderResponseError.from_message(
                code="invalid_video_response",
                message="Veo returned a non-object JSON response.",
                retriable=True,
                failure_step="video_generation",
            )
        return decoded

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}


def _standard_transport(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None
) -> VideoHttpResponse:
    """Execute a request through the standard library without logging secrets."""

    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=120) as response:  # noqa: S310
            return VideoHttpResponse(response.status, response.read())
    except HTTPError as error:
        return VideoHttpResponse(error.code, error.read())
    except (TimeoutError, URLError) as error:
        raise ProviderUnavailableError.from_message(
            code="video_network_error",
            message="Veo could not be reached.",
            retriable=True,
            failure_step="video_generation",
        ) from error


def _require_success(response: VideoHttpResponse) -> None:
    if response.status_code >= 500:
        raise ProviderUnavailableError.from_message(
            code="video_provider_server_error",
            message="Veo returned a transient server error.",
            retriable=True,
            failure_step="video_generation",
        )
    if response.status_code >= 400:
        raise ProviderUnavailableError.from_message(
            code="video_provider_request_failed",
            message="Veo rejected the video generation request.",
            retriable=False,
            failure_step="video_generation",
        )
