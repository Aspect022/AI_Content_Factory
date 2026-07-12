"""Typed records persisted by the SQLite repository layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """A generated file associated with a durable pipeline run."""

    artifact_id: str
    run_id: str
    artifact_type: str
    local_path: Path
    checksum: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProviderHealthRecord:
    """The last durable health observation for one provider."""

    provider_name: str
    status: str
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class AnalyticsRecord:
    """A monthly analytics snapshot used by a future reporting milestone."""

    month: str
    views: int | None
    impressions: int | None
    ctr: float | None
    avg_view_duration: float | None
    likes: int | None
    comments: int | None
    shares: int | None
    best_topic: str | None
    best_hook: str | None
    judge_summary: str | None
