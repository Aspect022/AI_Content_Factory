"""OpenRouter's documented asynchronous video generation provider."""

from __future__ import annotations

import json
from pathlib import Path

from app.exceptions import ProviderResponseError, ProviderUnavailableError
from app.providers.base import ProviderHealth, VideoGenerationRequest, VideoJob
from app.providers.veo_provider import (
    VideoHttpResponse,
    VideoTransport,
    _standard_transport,
)


class OpenRouterVideoProvider:
    """Generate video only through OpenRouter's asynchronous videos API."""

    _base_url = "https://openrouter.ai/api/v1/videos"

    def __init__(
        self,
        api_key: str,
        *,
        name: str,
        priority: int,
        model: str,
        transport: VideoTransport | None = None,
    ) -> None:
        """Create a model-configured provider with an injectable HTTP transport."""

        self._api_key = api_key
        self.name = name
        self.priority = priority
        self.model = model
        self._transport = transport or _standard_transport

    def health_check(self) -> ProviderHealth:
        """Report configured readiness without spending credits on a network probe."""

        from datetime import UTC, datetime

        return ProviderHealth(
            available=bool(self._api_key) and bool(self.model),
            checked_at=datetime.now(UTC),
            reason=(
                None
                if self._api_key and self.model
                else "OpenRouter is not configured."
            ),
        )

    def can_accept(self, request: VideoGenerationRequest) -> bool:
        """Accept a configuration-selected OpenRouter video model request."""

        return self.health_check().available and bool(request.prompt)

    def create_job(self, request: VideoGenerationRequest) -> VideoJob:
        """Submit a documented POST /videos request and return its async job ID."""

        if not self.can_accept(request):
            raise ProviderUnavailableError.from_message(
                code="openrouter_video_unavailable",
                message=(
                    "OpenRouter video generation is not configured for this request."
                ),
                retriable=False,
                failure_step="video_generation",
            )
        response = self._request_json(
            "POST",
            self._base_url,
            {
                "model": self.model,
                "prompt": request.prompt,
                "aspect_ratio": request.aspect_ratio,
                "duration": request.duration_seconds,
                "resolution": "720p",
            },
        )
        job_id = response.get("id")
        status = response.get("status")
        if not isinstance(job_id, str) or not isinstance(status, str):
            raise ProviderResponseError.from_message(
                code="invalid_openrouter_video_job",
                message="OpenRouter did not return a valid video job.",
                retriable=True,
                failure_step="video_generation",
            )
        return VideoJob(job_id=job_id, status=status, model=self.model)

    def poll_job(self, job_id: str) -> VideoJob:
        """Poll the documented OpenRouter job endpoint until a terminal state."""

        response = self._request_json("GET", f"{self._base_url}/{job_id}", None)
        status = response.get("status")
        if not isinstance(status, str):
            raise ProviderResponseError.from_message(
                code="invalid_openrouter_video_status",
                message="OpenRouter did not return a video job status.",
                retriable=True,
                failure_step="video_generation",
            )
        if status == "failed":
            raise ProviderUnavailableError.from_message(
                code="openrouter_video_failed",
                message="OpenRouter reported that video generation failed.",
                retriable=False,
                failure_step="video_generation",
            )
        return VideoJob(job_id=job_id, status=status, model=self.model)

    def download_result(self, job_id: str, target_path: Path) -> Path:
        """Download the first completed MP4 to the supplied runner-local path."""

        response = self._request_json("GET", f"{self._base_url}/{job_id}", None)
        urls = response.get("unsigned_urls")
        if not isinstance(urls, list) or not urls or not isinstance(urls[0], str):
            raise ProviderResponseError.from_message(
                code="openrouter_video_result_missing",
                message="OpenRouter did not return a downloadable video URL.",
                retriable=True,
                failure_step="video_download",
            )
        video_response = self._transport("GET", urls[0], self._headers(), None)
        _require_success(video_response)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(video_response.body)
        return target_path

    def _request_json(
        self, method: str, url: str, payload: dict[str, object] | None
    ) -> dict[str, object]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        response = self._transport(method, url, self._headers(), body)
        _require_success(response)
        try:
            decoded = json.loads(response.body)
        except json.JSONDecodeError as error:
            raise ProviderResponseError.from_message(
                code="invalid_openrouter_video_response",
                message="OpenRouter returned invalid JSON.",
                retriable=True,
                failure_step="video_generation",
            ) from error
        if not isinstance(decoded, dict):
            raise ProviderResponseError.from_message(
                code="invalid_openrouter_video_response",
                message="OpenRouter returned a non-object response.",
                retriable=True,
                failure_step="video_generation",
            )
        return decoded

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }


def _require_success(response: VideoHttpResponse) -> None:
    if response.status_code == 429 or response.status_code >= 500:
        raise ProviderUnavailableError.from_message(
            code="openrouter_video_transient_failure",
            message="OpenRouter video generation is temporarily unavailable.",
            retriable=True,
            failure_step="video_generation",
        )
    if response.status_code >= 400:
        raise ProviderUnavailableError.from_message(
            code="openrouter_video_request_failed",
            message="OpenRouter rejected the video request.",
            retriable=False,
            failure_step="video_generation",
        )
