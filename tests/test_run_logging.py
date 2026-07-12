"""Tests for JSON, SQLite, and stdout-compatible structured run logging."""

import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest

from app.exceptions import ErrorInfo
from app.logging.logger import RunLogger
from app.types import RunStatus


def test_run_logger_persists_a_successful_run_to_sqlite_and_json(
    tmp_path: Path,
) -> None:
    """A run update is written consistently to both required durable targets."""

    database_path = tmp_path / "data" / "database.sqlite"
    log_directory = tmp_path / "data" / "runs"
    logger = RunLogger(database_path, log_directory)

    started = logger.start_run(date(2026, 7, 12))
    completed = logger.update_run(
        started,
        status=RunStatus.UPLOADED,
        provider="veo_3_1_fast",
        model="Veo 3.1 Fast",
        topic="Sleep and phone screens",
        title="Sleep short",
        youtube_url="https://youtube.example/watch?v=abc",
        duration_seconds=18,
        generation_seconds=212.5,
    )

    with closing(sqlite3.connect(database_path)) as connection:
        stored = connection.execute(
            "SELECT status, provider, model, youtube_url FROM runs WHERE run_id = ?",
            (completed.run_id,),
        ).fetchone()
    log_path = log_directory / f"2026-07-12-{completed.run_id}.json"
    json_record = json.loads(log_path.read_text(encoding="utf-8"))

    assert stored == (
        "uploaded",
        "veo_3_1_fast",
        "Veo 3.1 Fast",
        "https://youtube.example/watch?v=abc",
    )
    assert json_record == completed.to_dict()


def test_run_logger_persists_structured_failure(tmp_path: Path) -> None:
    """A failed run stores an immediate, machine-readable failure description."""

    database_path = tmp_path / "data" / "database.sqlite"
    log_directory = tmp_path / "data" / "runs"
    logger = RunLogger(database_path, log_directory)
    started = logger.start_run(date(2026, 7, 12))
    error = ErrorInfo(
        code="provider_unavailable",
        message="The provider did not accept a generation request.",
        retriable=True,
        failure_step="video_generation",
    )

    failed = logger.update_run(
        started,
        status=RunStatus.FAILED,
        provider="veo_3_1_fast",
        model="Veo 3.1 Fast",
        failure_step="video_generation",
        error=error,
        retry_count=1,
    )

    with closing(sqlite3.connect(database_path)) as connection:
        error_json = connection.execute(
            "SELECT error_json FROM runs WHERE run_id = ?", (failed.run_id,)
        ).fetchone()[0]

    assert json.loads(error_json) == error.to_dict()


def test_run_logger_rejects_a_failure_without_error_information(tmp_path: Path) -> None:
    """Failure state cannot be persisted without structured error metadata."""

    logger = RunLogger(tmp_path / "database.sqlite", tmp_path / "runs")
    started = logger.start_run()

    with pytest.raises(ValueError, match="structured error"):
        logger.update_run(started, status=RunStatus.FAILED, failure_step="upload")
