"""Generate one video through a router and return a standardized local artifact."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

from app.exceptions import ProviderUnavailableError
from app.providers.base import VideoGenerationRequest, VideoProvider
from app.providers.router import ProviderRouter


@dataclass(frozen=True, slots=True)
class VideoResult:
    """A completed provider video stored at a runner-local MP4 path."""

    provider: str
    model: str
    job_id: str
    local_path: Path
    duration_seconds: int
    generation_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def local_mp4_path(self) -> Path:
        """Return the standardized runner-local MP4 path."""

        return self.local_path


class VideoGenerationService:
    """Keep provider selection and polling outside the orchestrator."""

    def __init__(
        self,
        router: ProviderRouter[VideoProvider],
        *,
        sleep: Callable[[float], None],
        poll_interval_seconds: float = 30,
    ) -> None:
        """Create a service with an injectable wait function for testability."""

        self._router = router
        self._sleep = sleep
        self._poll_interval_seconds = poll_interval_seconds

    def generate(
        self, request: VideoGenerationRequest, target_path: Path
    ) -> VideoResult:
        """Generate, poll, and save one video without exposing providers upstream."""

        started_at = monotonic()

        def operation(provider: VideoProvider) -> VideoResult:
            if not provider.can_accept(request):
                raise ProviderUnavailableError.from_message(
                    code="video_provider_cannot_accept",
                    message="The provider cannot accept this video request.",
                    retriable=False,
                    failure_step="video_generation",
                )
            job = provider.create_job(request)
            while job.status not in {"completed", "failed"}:
                self._sleep(self._poll_interval_seconds)
                job = provider.poll_job(job.job_id)
            if job.status == "failed":
                raise ProviderUnavailableError.from_message(
                    code="video_generation_failed",
                    message="The video provider reported a failed job.",
                    retriable=False,
                    failure_step="video_generation",
                )
            local_path = provider.download_result(job.job_id, target_path)
            return VideoResult(
                provider=provider.name,
                model=job.model,
                job_id=job.job_id,
                local_path=local_path,
                duration_seconds=request.duration_seconds,
                metadata={
                    "aspect_ratio": request.aspect_ratio,
                    "source_image": request.source_image_path is not None,
                },
            )

        result = self._router.execute(operation).value
        return VideoResult(
            provider=result.provider,
            model=result.model,
            job_id=result.job_id,
            local_path=result.local_path,
            duration_seconds=result.duration_seconds,
            generation_seconds=monotonic() - started_at,
            metadata=result.metadata,
        )
