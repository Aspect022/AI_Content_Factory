"""Tests for provider-neutral upload handoff and temporary MP4 lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.content.generation import Script, Topic
from app.exceptions import UploadError
from app.logging.logger import RunLogger
from app.orchestrator import DailyOrchestrator
from app.providers.base import NotificationRequest, UploadRequest, UploadResponse
from app.types import RunStatus
from app.video.generation import VideoResult

TOPIC = Topic("hi", "Sleep", "Sleep topic", "Sleep hook", 8)
SCRIPT = Script(
    topic="Sleep topic",
    hook="Sleep hook",
    script="Hindi script",
    title="Sleep title",
    description="Description",
    hashtags=("#shorts",),
    visual_prompt="Visual prompt",
    voice_prompt="Voice prompt",
    safety_notes=("Education only",),
    estimated_seconds=8,
)


class FakeContentGenerator:
    def generate_topic(self, _pillar: str | None = None) -> Topic:
        return TOPIC

    def generate_script(self, _topic: Topic) -> Script:
        return SCRIPT


@dataclass
class FakeVideoGenerator:
    fail: bool = False

    def generate(self, _request: object, target_path: Path) -> VideoResult:
        if self.fail:
            raise UploadError.from_message(
                code="video_failed", message="Video failed", retriable=False
            )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"mp4")
        return VideoResult("openrouter", "configured/model", "job", target_path, 8)


@dataclass
class FakeUploader:
    fail: bool = False

    def upload(self, request: UploadRequest) -> UploadResponse:
        if self.fail:
            raise UploadError.from_message(
                code="upload_failed", message="Upload failed", retriable=False
            )
        assert request.video_path.exists()
        return UploadResponse("video-id", "https://youtube.example/video-id")


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, request: NotificationRequest) -> None:
        self.messages.append(request.message)


def test_complete_mock_pipeline_deletes_video_only_after_upload(tmp_path: Path) -> None:
    """Integration: topic, script, video, upload, notification, logs, and cleanup."""

    notifier = FakeNotifier()
    orchestrator = DailyOrchestrator(
        content_generator=FakeContentGenerator(),  # type: ignore[arg-type]
        video_generator=FakeVideoGenerator(),  # type: ignore[arg-type]
        uploader=FakeUploader(),  # type: ignore[arg-type]
        notifier=notifier,  # type: ignore[arg-type]
        run_logger=RunLogger(tmp_path / "database.sqlite", tmp_path / "runs"),
        temporary_video_directory=tmp_path / "videos",
    )

    result = orchestrator.run()

    assert result.run_log.status is RunStatus.UPLOADED
    assert result.video is not None
    assert not result.video.local_path.exists()
    assert "Upload succeeded" in notifier.messages[0]


def test_orchestrator_preserves_temporary_video_when_upload_fails(
    tmp_path: Path,
) -> None:
    """A failed upload keeps the local MP4 for workflow artifact collection."""

    notifier = FakeNotifier()
    orchestrator = DailyOrchestrator(
        content_generator=FakeContentGenerator(),  # type: ignore[arg-type]
        video_generator=FakeVideoGenerator(),  # type: ignore[arg-type]
        uploader=FakeUploader(fail=True),  # type: ignore[arg-type]
        notifier=notifier,  # type: ignore[arg-type]
        run_logger=RunLogger(tmp_path / "database.sqlite", tmp_path / "runs"),
        temporary_video_directory=tmp_path / "videos",
    )

    result = orchestrator.run()

    assert result.run_log.status is RunStatus.FAILED
    assert result.video is not None
    assert result.video.local_path.exists()
    assert "Pipeline failed" in notifier.messages[0]
