"""Immutable SQLite schema migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Migration:
    """One ordered, immutable database schema change."""

    version: int
    name: str
    sql: str


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="create_core_pipeline_tables",
        sql="""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            run_date TEXT NOT NULL,
            status TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            topic TEXT,
            title TEXT,
            script_hash TEXT,
            video_hash TEXT,
            youtube_url TEXT,
            duration_seconds INTEGER,
            generation_seconds REAL,
            retry_count INTEGER NOT NULL CHECK (retry_count >= 0),
            failure_step TEXT,
            error_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(run_id),
            artifact_type TEXT NOT NULL,
            local_path TEXT NOT NULL,
            checksum TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS analytics (
            month TEXT PRIMARY KEY,
            views INTEGER,
            impressions INTEGER,
            ctr REAL,
            avg_view_duration REAL,
            likes INTEGER,
            comments INTEGER,
            shares INTEGER,
            best_topic TEXT,
            best_hook TEXT,
            judge_summary TEXT
        );

        CREATE TABLE IF NOT EXISTS provider_health (
            provider_name TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            last_checked_at TEXT,
            last_success_at TEXT,
            last_error TEXT
        );
        """,
    ),
)


def apply_migrations(database_path: Path) -> None:
    """Apply all pending migrations to the SQLite database.

    Args:
        database_path: Location of the SQLite database file.
    """

    database_path.parent.mkdir(parents=True, exist_ok=True)
    with _database_connection(database_path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        applied_versions = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        for migration in MIGRATIONS:
            if migration.version in applied_versions:
                continue
            connection.executescript(migration.sql)
            connection.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (migration.version, migration.name),
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
