"""Tests for parameterized SQLite repositories over the required core tables."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

from app.storage.models import AnalyticsRecord, ArtifactRecord, ProviderHealthRecord
from app.storage.sqlite import (
    AnalyticsRepository,
    ArtifactRepository,
    ProviderHealthRepository,
    RunRepository,
)
from app.types import RunLog, RunStatus


def test_artifact_repository_persists_artifacts_for_a_run(tmp_path: Path) -> None:
    """Artifact records are stored and queried using the owning run ID."""

    database_path = tmp_path / "database.sqlite"
    timestamp = datetime.now(UTC)
    run = RunLog(
        run_id="run-1",
        date=date(2026, 7, 12),
        status=RunStatus.RUNNING,
        provider=None,
        model=None,
        topic=None,
        title=None,
        script_hash=None,
        video_hash=None,
        youtube_url=None,
        duration_seconds=None,
        generation_seconds=None,
        retry_count=0,
        failure_step=None,
        error=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    run_repository = RunRepository(database_path)
    run_repository.insert(run)
    repository = ArtifactRepository(database_path)
    artifact = ArtifactRecord(
        artifact_id="artifact-1",
        run_id=run.run_id,
        artifact_type="script",
        local_path=Path("data/runs/run-1.json"),
        checksum="abc123",
        created_at=timestamp,
    )

    repository.insert(artifact)

    assert repository.list_for_run(run.run_id) == [artifact]
    assert run_repository.get(run.run_id) is not None


def test_provider_health_repository_upserts_a_provider_observation(
    tmp_path: Path,
) -> None:
    """A later health signal replaces the prior row for the same provider."""

    database_path = tmp_path / "database.sqlite"
    repository = ProviderHealthRepository(database_path)
    first = ProviderHealthRecord(
        provider_name="mock-text",
        status="unavailable",
        last_checked_at=datetime(2026, 7, 12, tzinfo=UTC),
        last_success_at=None,
        last_error="timeout",
    )
    second = ProviderHealthRecord(
        provider_name="mock-text",
        status="available",
        last_checked_at=datetime(2026, 7, 12, 1, tzinfo=UTC),
        last_success_at=datetime(2026, 7, 12, 1, tzinfo=UTC),
        last_error=None,
    )

    repository.upsert(first)
    repository.upsert(second)

    assert repository.get("mock-text") == second
    assert repository.get("missing") is None


def test_analytics_repository_upserts_monthly_snapshot(tmp_path: Path) -> None:
    """A monthly analytics record can be replaced without unsafe SQL formatting."""

    repository = AnalyticsRepository(tmp_path / "database.sqlite")
    record = AnalyticsRecord(
        month="2026-07",
        views=100,
        impressions=500,
        ctr=0.2,
        avg_view_duration=16.5,
        likes=10,
        comments=2,
        shares=3,
        best_topic="Sleep",
        best_hook="A fast hook",
        judge_summary="Use more sleep topics.",
    )

    repository.upsert(record)
    repository.upsert(replace(record, views=150))

    stored = repository.get("2026-07")
    assert stored is not None
    assert stored.views == 150
    assert repository.get("missing") is None
