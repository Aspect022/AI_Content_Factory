"""OpenRouter's documented asynchronous video generation provider."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

from app.exceptions import ProviderResponseError, ProviderUnavailableError
from app.providers.base import ProviderHealth, VideoGenerationRequest, VideoJob
from app.providers.veo_provider import (
    VideoHttpResponse,
    VideoTransport,
    _standard_transport,
)
from app.providers.video_diagnostics import log_http_failure, request_started


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
        self._jobs: dict[str, dict[str, object]] = {}

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
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": request.prompt,
            "aspect_ratio": request.aspect_ratio,
            "duration": request.duration_seconds,
            "resolution": "720p",
            "generate_audio": True,
        }
        if request.source_image_path is not None:
            mime_type = (
                mimetypes.guess_type(request.source_image_path.name)[0] or "image/png"
            )
            payload["frame_images"] = [
                {
                    "frame_type": "first_frame",
                    "data": base64.b64encode(
                        request.source_image_path.read_bytes()
                    ).decode("ascii"),
                    "mime_type": mime_type,
                }
            ]
        response = self._request_json(
            "POST",
            self._base_url,
            payload,
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
        polling_url = response.get("polling_url")
        if not isinstance(polling_url, str) or not polling_url:
            polling_url = f"{self._base_url}/{job_id}"
        self._jobs[job_id] = {"polling_url": self._absolute_url(polling_url)}
        return VideoJob(job_id=job_id, status=status, model=self.model)

    def poll_job(self, job_id: str) -> VideoJob:
        """Poll the documented OpenRouter job endpoint until a terminal state."""

        response = self._request_json(
            "GET", self._polling_url(job_id), None, job_id=job_id
        )
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
        self._jobs.setdefault(job_id, {})["last_status"] = status
        urls = response.get("unsigned_urls")
        if isinstance(urls, list) and urls and isinstance(urls[0], str):
            self._jobs[job_id]["download_url"] = urls[0]
        return VideoJob(job_id=job_id, status=status, model=self.model)

    def download_result(self, job_id: str, target_path: Path) -> Path:
        """Download the first completed MP4 to the supplied runner-local path."""

        state = self._jobs.get(job_id, {})
        download_url = state.get("download_url")
        if not isinstance(download_url, str):
            download_url = f"{self._base_url}/{job_id}/content?index=0"
        started_at = request_started()
        video_response = self._transport("GET", download_url, self._headers(), None)
        _require_success(
            video_response,
            provider=self.name,
            model=self.model,
            endpoint=download_url,
            started_at=started_at,
            polling_status=(
                state.get("last_status")
                if isinstance(state.get("last_status"), str)
                else None
            ),
            job_id=job_id,
            download_url=download_url,
            failure_step="video_download",
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(video_response.body)
        return target_path

    def _request_json(
        self,
        method: str,
        url: str,
        payload: dict[str, object] | None,
        *,
        job_id: str | None = None,
    ) -> dict[str, object]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        started_at = request_started()
        response = self._transport(method, url, self._headers(), body)
        state = self._jobs.get(job_id or "", {})
        _require_success(
            response,
            provider=self.name,
            model=self.model,
            endpoint=url,
            started_at=started_at,
            polling_status=(
                state.get("last_status")
                if isinstance(state.get("last_status"), str)
                else None
            ),
            job_id=job_id,
            download_url=(
                state.get("download_url")
                if isinstance(state.get("download_url"), str)
                else None
            ),
            failure_step="video_generation",
        )
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

    def _polling_url(self, job_id: str) -> str:
        """Return the provider-supplied polling URL, or its documented fallback."""

        url = self._jobs.get(job_id, {}).get("polling_url")
        return url if isinstance(url, str) else f"{self._base_url}/{job_id}"

    def _absolute_url(self, url: str) -> str:
        """Resolve an API-relative polling URL returned by OpenRouter."""

        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"https://openrouter.ai{url if url.startswith('/') else '/' + url}"


def _require_success(
    response: VideoHttpResponse,
    *,
    provider: str,
    model: str,
    endpoint: str,
    started_at: float,
    polling_status: str | None,
    job_id: str | None,
    download_url: str | None,
    failure_step: str,
) -> None:
    if response.status_code >= 400:
        transient = response.status_code in {429, 500, 502, 503, 504}
        log_http_failure(
            provider=provider,
            model=model,
            endpoint=endpoint,
            status_code=response.status_code,
            response_body=response.body,
            started_at=started_at,
            polling_status=polling_status,
            job_id=job_id,
            download_url=download_url,
        )
        raise ProviderUnavailableError.from_message(
            code=(
                "openrouter_video_transient_failure"
                if transient
                else "openrouter_video_request_failed"
            ),
            message=(
                "OpenRouter video generation is temporarily unavailable."
                if transient
                else "OpenRouter rejected the video request."
            ),
            retriable=transient,
            failure_step=failure_step,
        )
