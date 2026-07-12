"""Core typed models for run state and durable logging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.exceptions import ErrorInfo


class RunStatus(StrEnum):
    """The durable lifecycle states of a daily pipeline run."""

    RUNNING = "running"
    UPLOADED = "uploaded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RunLog:
    """A complete, serializable record of one daily pipeline execution."""

    run_id: str
    date: date
    status: RunStatus
    provider: str | None
    model: str | None
    topic: str | None
    title: str | None
    script_hash: str | None
    video_hash: str | None
    youtube_url: str | None
    duration_seconds: int | None
    generation_seconds: float | None
    retry_count: int
    failure_step: str | None
    error: ErrorInfo | None
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, object]:
        """Return the run log using the repository's JSON log contract."""

        return {
            "run_id": self.run_id,
            "date": self.date.isoformat(),
            "status": self.status.value,
            "provider": self.provider,
            "model": self.model,
            "topic": self.topic,
            "title": self.title,
            "script_hash": self.script_hash,
            "video_hash": self.video_hash,
            "youtube_url": self.youtube_url,
            "duration_seconds": self.duration_seconds,
            "generation_seconds": self.generation_seconds,
            "retry_count": self.retry_count,
            "failure_step": self.failure_step,
            "error": None if self.error is None else self.error.to_dict(),
            "timestamp": self.created_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
