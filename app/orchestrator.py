"""Provider-neutral daily pipeline orchestration and temporary-file lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.content.generation import ContentGenerator, Script
from app.exceptions import ApplicationError, NotificationError
from app.logging.logger import RunLogger
from app.providers.base import (
    NotificationProvider,
    NotificationRequest,
    UploadProvider,
    UploadRequest,
    VideoGenerationRequest,
)
from app.types import RunLog, RunStatus
from app.video.generation import VideoGenerationService, VideoResult


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Durable final state of one orchestrated pipeline run."""

    run_log: RunLog
    video: VideoResult | None


class DailyOrchestrator:
    """Coordinate services through contracts without calling concrete providers."""

    def __init__(
        self,
        *,
        content_generator: ContentGenerator,
        video_generator: VideoGenerationService,
        uploader: UploadProvider,
        notifier: NotificationProvider,
        run_logger: RunLogger,
        temporary_video_directory: Path,
        youtube_category_id: str = "22",
        youtube_privacy_status: str = "private",
    ) -> None:
        """Create an orchestrator from services and provider-neutral interfaces."""

        self._content_generator = content_generator
        self._video_generator = video_generator
        self._uploader = uploader
        self._notifier = notifier
        self._run_logger = run_logger
        self._temporary_video_directory = temporary_video_directory
        self._youtube_category_id = youtube_category_id
        self._youtube_privacy_status = youtube_privacy_status

    def run(self, pillar: str | None = None) -> PipelineResult:
        """Generate, upload, log, notify, and clean up one daily video artifact."""

        run_log = self._run_logger.start_run()
        video: VideoResult | None = None
        try:
            topic = self._content_generator.generate_topic(pillar)
            script = self._content_generator.generate_script(topic)
            video = self._generate_video(script)
            upload = self._uploader.upload(
                UploadRequest(
                    video_path=video.local_path,
                    title=script.title,
                    description=script.description,
                    tags=script.hashtags,
                    category_id=self._youtube_category_id,
                    privacy_status=self._youtube_privacy_status,
                )
            )
            run_log = self._run_logger.update_run(
                run_log,
                status=RunStatus.UPLOADED,
                provider=video.provider,
                model=video.model,
                topic=topic.topic,
                title=script.title,
                youtube_url=upload.url,
                duration_seconds=video.duration_seconds,
                generation_seconds=video.generation_seconds,
            )
            video.local_path.unlink(missing_ok=True)
            self._notify(
                f"Upload succeeded\nProvider: {video.provider}\n"
                f"Generation: {video.generation_seconds:.1f}s\n"
                f"YouTube: {upload.url}"
            )
            return PipelineResult(run_log=run_log, video=video)
        except ApplicationError as error:
            run_log = self._run_logger.update_run(
                run_log,
                status=RunStatus.FAILED,
                provider=None if video is None else video.provider,
                model=None if video is None else video.model,
                failure_step=error.error.failure_step or "pipeline",
                error=error.error,
            )
            self._notify_failure(error)
            return PipelineResult(run_log=run_log, video=video)

    def _generate_video(self, script: Script) -> VideoResult:
        target_path = self._temporary_video_directory / f"{uuid4()}.mp4"
        return self._video_generator.generate(
            VideoGenerationRequest(prompt=script.visual_prompt), target_path
        )

    def _notify(self, message: str) -> None:
        try:
            self._notifier.send(NotificationRequest(message=message))
        except NotificationError:
            return

    def _notify_failure(self, error: ApplicationError) -> None:
        self._notify(
            f"Pipeline failed at {error.error.failure_step}: {error.error.message}"
        )
