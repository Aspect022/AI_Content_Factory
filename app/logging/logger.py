"""Structured stdout logging and dual durable run-log persistence."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from app.storage.sqlite import RunRepository
from app.types import RunLog, RunStatus


def configure_structured_logging(level: str = "INFO") -> None:
    """Configure stdout to emit one JSON object per application log event.

    Args:
        level: Standard Python logging level name.
    """

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    application_logger = logging.getLogger("ai_shorts_factory")
    application_logger.handlers.clear()
    application_logger.addHandler(handler)
    application_logger.setLevel(level)
    application_logger.propagate = False


class RunLogger:
    """Keep the SQLite record and versionable JSON run artifact synchronized."""

    def __init__(self, database_path: Path, run_log_directory: Path) -> None:
        """Create a logger backed by the required SQLite and JSON destinations."""

        self._repository = RunRepository(database_path)
        self._run_log_directory = run_log_directory
        self._run_log_directory.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger("ai_shorts_factory.run")

    def start_run(self, run_date: date | None = None) -> RunLog:
        """Create and durably persist a new running pipeline record.

        Args:
            run_date: The content date, defaulting to the current UTC date.

        Returns:
            A running log record with a unique identifier.
        """

        timestamp = datetime.now(UTC)
        record = RunLog(
            run_id=str(uuid4()),
            date=run_date or timestamp.date(),
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
        self._repository.insert(record)
        self._write_json(record)
        self._emit("run_started", record)
        return record

    def update_run(self, record: RunLog, **changes: object) -> RunLog:
        """Persist a changed run state to SQLite, JSON, and structured stdout.

        Args:
            record: Existing canonical run log.
            **changes: Dataclass fields to replace in the record.

        Returns:
            The updated and durably persisted record.
        """

        updated = replace(record, **changes, updated_at=datetime.now(UTC))
        self._validate(updated)
        self._repository.update(updated)
        self._write_json(updated)
        self._emit("run_updated", updated)
        return updated

    def _write_json(self, record: RunLog) -> None:
        destination = (
            self._run_log_directory / f"{record.date.isoformat()}-{record.run_id}.json"
        )
        temporary_destination = destination.with_suffix(".json.tmp")
        temporary_destination.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        temporary_destination.replace(destination)

    def _emit(self, event: str, record: RunLog) -> None:
        self._logger.info(
            json.dumps(
                {
                    "event": event,
                    "run_id": record.run_id,
                    "status": record.status.value,
                    "provider": record.provider,
                    "model": record.model,
                    "retry_count": record.retry_count,
                },
                sort_keys=True,
            )
        )

    @staticmethod
    def _validate(record: RunLog) -> None:
        if record.retry_count < 0:
            raise ValueError("retry_count cannot be negative")
        if record.status is RunStatus.FAILED and record.error is None:
            raise ValueError("failed runs require structured error information")
        if record.status is not RunStatus.FAILED and record.error is not None:
            raise ValueError("only failed runs may have error information")
        if record.error is not None and record.failure_step is None:
            raise ValueError("failed runs require a failure_step")
