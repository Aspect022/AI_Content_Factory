"""Official Gemini Omni Flash video adapter using the Interactions API."""

from __future__ import annotations

import base64
import json
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.exceptions import ProviderResponseError, ProviderUnavailableError
from app.providers.base import ProviderHealth, VideoGenerationRequest, VideoJob
from app.providers.veo_provider import (
    VideoHttpResponse,
    VideoTransport,
    _standard_transport,
)
from app.providers.video_diagnostics import log_http_failure, request_started


class GeminiOmniVideoProvider:
    """Create a single Gemini Omni Flash video through the official REST API."""

    _endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(
        self,
        api_key: str,
        *,
        name: str,
        priority: int,
        model: str,
        transport: VideoTransport | None = None,
    ) -> None:
        """Create a configuration-selected adapter with an injectable transport."""

        self._api_key = api_key
        self.name = name
        self.priority = priority
        self.model = model
        self._transport = transport or _standard_transport
        self._completed_videos: dict[str, bytes] = {}

    def health_check(self) -> ProviderHealth:
        """Report configuration readiness without spending quota on a probe."""

        return ProviderHealth(
            available=bool(self._api_key) and bool(self.model),
            checked_at=datetime.now(UTC),
            reason=(
                None
                if self._api_key and self.model
                else "Gemini Omni is not configured."
            ),
        )

    def can_accept(self, request: VideoGenerationRequest) -> bool:
        """Accept documented text-to-video or local image-to-video requests."""

        return (
            self.health_check().available
            and bool(request.prompt)
            and request.aspect_ratio in {"9:16", "16:9"}
            and (
                request.source_image_path is None or request.source_image_path.is_file()
            )
        )

    def create_job(self, request: VideoGenerationRequest) -> VideoJob:
        """Submit an interaction and retain its returned MP4 bytes by job ID."""

        if not self.can_accept(request):
            raise ProviderUnavailableError.from_message(
                code="gemini_omni_video_unavailable",
                message="Gemini Omni cannot accept this video request.",
                retriable=False,
                failure_step="video_generation",
            )
        payload = {
            "model": self.model,
            "input": self._input(request),
            "response_format": {"type": "video", "aspect_ratio": request.aspect_ratio},
        }
        if request.source_image_path is not None:
            payload["generation_config"] = {"video_config": {"task": "image_to_video"}}
        response = self._request_json("POST", payload)
        job_id = response.get("id")
        if not isinstance(job_id, str) or not job_id:
            job_id = str(uuid4())
        video_data = _extract_video_data(response)
        try:
            self._completed_videos[job_id] = base64.b64decode(video_data, validate=True)
        except (ValueError, TypeError) as error:
            raise ProviderResponseError.from_message(
                code="invalid_gemini_omni_video_data",
                message="Gemini Omni returned invalid base64 video data.",
                retriable=True,
                failure_step="video_generation",
            ) from error
        return VideoJob(
            job_id=job_id,
            status="completed",
            model=self.model,
            duration_seconds=request.duration_seconds,
        )

    def poll_job(self, job_id: str) -> VideoJob:
        """Return the completed interaction retained by the synchronous API call."""

        if job_id not in self._completed_videos:
            raise ProviderResponseError.from_message(
                code="unknown_gemini_omni_video_job",
                message="Gemini Omni video job data is unavailable.",
                retriable=True,
                failure_step="video_generation",
            )
        return VideoJob(job_id=job_id, status="completed", model=self.model)

    def download_result(self, job_id: str, target_path: Path) -> Path:
        """Write the interaction's returned MP4 bytes to the runner workspace."""

        video = self._completed_videos.pop(job_id, None)
        if video is None:
            raise ProviderResponseError.from_message(
                code="gemini_omni_video_result_missing",
                message="Gemini Omni did not retain a downloadable video result.",
                retriable=True,
                failure_step="video_download",
            )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(video)
        return target_path

    def _input(self, request: VideoGenerationRequest) -> object:
        if request.source_image_path is None:
            return request.prompt
        mime_type = (
            mimetypes.guess_type(request.source_image_path.name)[0] or "image/png"
        )
        image = base64.b64encode(request.source_image_path.read_bytes()).decode("ascii")
        return [
            {"type": "image", "data": image, "mime_type": mime_type},
            {"type": "text", "text": request.prompt},
        ]

    def _request_json(
        self, method: str, payload: dict[str, object]
    ) -> dict[str, object]:
        started_at = request_started()
        response = self._transport(
            method,
            self._endpoint,
            {"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
            json.dumps(payload).encode("utf-8"),
        )
        _require_success(response, self.name, self.model, self._endpoint, started_at)
        try:
            decoded = json.loads(response.body)
        except json.JSONDecodeError as error:
            raise ProviderResponseError.from_message(
                code="invalid_gemini_omni_video_response",
                message="Gemini Omni returned invalid JSON.",
                retriable=True,
                failure_step="video_generation",
            ) from error
        if not isinstance(decoded, dict):
            raise ProviderResponseError.from_message(
                code="invalid_gemini_omni_video_response",
                message="Gemini Omni returned a non-object JSON response.",
                retriable=True,
                failure_step="video_generation",
            )
        return decoded


def _extract_video_data(response: dict[str, object]) -> str:
    """Extract the REST Interactions API video part documented by Gemini."""

    try:
        steps = response["steps"]
        for step in reversed(steps if isinstance(steps, list) else []):
            content = step.get("content", []) if isinstance(step, dict) else []
            for part in content if isinstance(content, list) else []:
                if isinstance(part, dict) and part.get("type") == "video":
                    data = part.get("data")
                    if isinstance(data, str) and data:
                        return data
    except (KeyError, TypeError):
        pass
    raise ProviderResponseError.from_message(
        code="gemini_omni_video_result_missing",
        message="Gemini Omni did not return a video result.",
        retriable=True,
        failure_step="video_generation",
    )


def _require_success(
    response: VideoHttpResponse,
    provider: str,
    model: str,
    endpoint: str,
    started_at: float,
) -> None:
    if response.status_code >= 400:
        body_text = response.body.decode("utf-8", errors="replace").lower()
        quota_exhausted = response.status_code == 429 and (
            "quota exceeded" in body_text or "limit: 0" in body_text
        )
        log_http_failure(
            provider=provider,
            model=model,
            endpoint=endpoint,
            status_code=response.status_code,
            response_body=response.body,
            started_at=started_at,
        )
        raise ProviderUnavailableError.from_message(
            code=(
                "gemini_omni_video_quota_exhausted"
                if quota_exhausted
                else (
                    "gemini_omni_video_transient_failure"
                    if response.status_code in {429, 500, 502, 503, 504}
                    else "gemini_omni_video_request_failed"
                )
            ),
            message=(
                "Gemini Omni has no API quota for this project."
                if quota_exhausted
                else (
                    "Gemini Omni video generation is temporarily unavailable."
                    if response.status_code in {429, 500, 502, 503, 504}
                    else "Gemini Omni rejected the video request."
                )
            ),
            retriable=(
                not quota_exhausted
                and response.status_code in {429, 500, 502, 503, 504}
            ),
            failure_step="video_generation",
        )
