"""SQLite persistence for canonical run logs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.storage.migrations import apply_migrations
from app.storage.models import AnalyticsRecord, ArtifactRecord, ProviderHealthRecord
from app.types import RunLog


class RunRepository:
    """Store and update run records with parameterized SQL statements."""

    def __init__(self, database_path: Path) -> None:
        """Initialize the repository and apply pending schema migrations."""

        self._database_path = database_path
        apply_migrations(database_path)

    def insert(self, record: RunLog) -> None:
        """Persist a new run record.

        Args:
            record: The initial run record to insert.
        """

        with _database_connection(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, run_date, status, provider, model, topic, title,
                    script_hash, video_hash, youtube_url, duration_seconds,
                    generation_seconds, retry_count, failure_step, error_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._as_row(record),
            )

    def update(self, record: RunLog) -> None:
        """Update a previously persisted run record.

        Args:
            record: The latest canonical run record.

        Raises:
            LookupError: If the run was never inserted.
        """

        with _database_connection(self._database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE runs
                SET status = ?, provider = ?, model = ?, topic = ?, title = ?,
                    script_hash = ?, video_hash = ?, youtube_url = ?,
                    duration_seconds = ?, generation_seconds = ?, retry_count = ?,
                    failure_step = ?, error_json = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (
                    record.status.value,
                    record.provider,
                    record.model,
                    record.topic,
                    record.title,
                    record.script_hash,
                    record.video_hash,
                    record.youtube_url,
                    record.duration_seconds,
                    record.generation_seconds,
                    record.retry_count,
                    record.failure_step,
                    self._error_json(record),
                    record.updated_at.isoformat(),
                    record.run_id,
                ),
            )
        if cursor.rowcount != 1:
            raise LookupError(f"Run record not found: {record.run_id}")

    def get(self, run_id: str) -> tuple[object, ...] | None:
        """Return the canonical database row for a run identifier."""

        with _database_connection(self._database_path) as connection:
            return connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()

    @staticmethod
    def _as_row(record: RunLog) -> tuple[object, ...]:
        return (
            record.run_id,
            record.date.isoformat(),
            record.status.value,
            record.provider,
            record.model,
            record.topic,
            record.title,
            record.script_hash,
            record.video_hash,
            record.youtube_url,
            record.duration_seconds,
            record.generation_seconds,
            record.retry_count,
            record.failure_step,
            RunRepository._error_json(record),
            record.created_at.isoformat(),
            record.updated_at.isoformat(),
        )

    @staticmethod
    def _error_json(record: RunLog) -> str | None:
        return (
            None
            if record.error is None
            else json.dumps(record.error.to_dict(), sort_keys=True)
        )


class ArtifactRepository:
    """Persist generated artifact records with parameterized SQL."""

    def __init__(self, database_path: Path) -> None:
        """Initialize the repository and apply pending schema migrations."""

        self._database_path = database_path
        apply_migrations(database_path)

    def insert(self, record: ArtifactRecord) -> None:
        """Store one artifact associated with an existing run."""

        with _database_connection(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO artifacts (
                    artifact_id, run_id, artifact_type, local_path, checksum, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.artifact_id,
                    record.run_id,
                    record.artifact_type,
                    str(record.local_path),
                    record.checksum,
                    record.created_at.isoformat(),
                ),
            )

    def list_for_run(self, run_id: str) -> list[ArtifactRecord]:
        """Return all artifacts for a run in creation order."""

        with _database_connection(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, run_id, artifact_type, local_path, checksum,
                       created_at
                FROM artifacts WHERE run_id = ? ORDER BY created_at
                """,
                (run_id,),
            ).fetchall()
        return [
            ArtifactRecord(
                artifact_id=row[0],
                run_id=row[1],
                artifact_type=row[2],
                local_path=Path(row[3]),
                checksum=row[4],
                created_at=datetime.fromisoformat(row[5]),
            )
            for row in rows
        ]


class ProviderHealthRepository:
    """Store the most recent availability signal for each provider."""

    def __init__(self, database_path: Path) -> None:
        """Initialize the repository and apply pending schema migrations."""

        self._database_path = database_path
        apply_migrations(database_path)

    def upsert(self, record: ProviderHealthRecord) -> None:
        """Create or replace one provider's latest health observation."""

        with _database_connection(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO provider_health (
                    provider_name, status, last_checked_at, last_success_at, last_error
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider_name) DO UPDATE SET
                    status = excluded.status,
                    last_checked_at = excluded.last_checked_at,
                    last_success_at = excluded.last_success_at,
                    last_error = excluded.last_error
                """,
                self._provider_health_row(record),
            )

    def get(self, provider_name: str) -> ProviderHealthRecord | None:
        """Return the last health record for a provider, if it exists."""

        with _database_connection(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT provider_name, status, last_checked_at, last_success_at,
                       last_error
                FROM provider_health WHERE provider_name = ?
                """,
                (provider_name,),
            ).fetchone()
        return None if row is None else self._provider_health_from_row(row)

    @staticmethod
    def _provider_health_row(record: ProviderHealthRecord) -> tuple[object, ...]:
        return (
            record.provider_name,
            record.status,
            (
                None
                if record.last_checked_at is None
                else record.last_checked_at.isoformat()
            ),
            (
                None
                if record.last_success_at is None
                else record.last_success_at.isoformat()
            ),
            record.last_error,
        )

    @staticmethod
    def _provider_health_from_row(row: tuple[object, ...]) -> ProviderHealthRecord:
        return ProviderHealthRecord(
            provider_name=str(row[0]),
            status=str(row[1]),
            last_checked_at=(
                None if row[2] is None else datetime.fromisoformat(str(row[2]))
            ),
            last_success_at=(
                None if row[3] is None else datetime.fromisoformat(str(row[3]))
            ),
            last_error=None if row[4] is None else str(row[4]),
        )


class AnalyticsRepository:
    """Store monthly analytics snapshots with parameterized SQL."""

    def __init__(self, database_path: Path) -> None:
        """Initialize the repository and apply pending schema migrations."""

        self._database_path = database_path
        apply_migrations(database_path)

    def upsert(self, record: AnalyticsRecord) -> None:
        """Create or replace the analytics snapshot for one month."""

        with _database_connection(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO analytics (
                    month, views, impressions, ctr, avg_view_duration, likes, comments,
                    shares, best_topic, best_hook, judge_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(month) DO UPDATE SET
                    views = excluded.views,
                    impressions = excluded.impressions,
                    ctr = excluded.ctr,
                    avg_view_duration = excluded.avg_view_duration,
                    likes = excluded.likes,
                    comments = excluded.comments,
                    shares = excluded.shares,
                    best_topic = excluded.best_topic,
                    best_hook = excluded.best_hook,
                    judge_summary = excluded.judge_summary
                """,
                self._analytics_row(record),
            )

    def get(self, month: str) -> AnalyticsRecord | None:
        """Return the analytics snapshot for a month, if it exists."""

        with _database_connection(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT month, views, impressions, ctr, avg_view_duration, likes,
                       comments,
                       shares, best_topic, best_hook, judge_summary
                FROM analytics WHERE month = ?
                """,
                (month,),
            ).fetchone()
        return None if row is None else AnalyticsRecord(*row)

    @staticmethod
    def _analytics_row(record: AnalyticsRecord) -> tuple[object, ...]:
        return (
            record.month,
            record.views,
            record.impressions,
            record.ctr,
            record.avg_view_duration,
            record.likes,
            record.comments,
            record.shares,
            record.best_topic,
            record.best_hook,
            record.judge_summary,
        )


@contextmanager
def _database_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a committed SQLite connection and close it on every code path."""

    connection = sqlite3.connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
