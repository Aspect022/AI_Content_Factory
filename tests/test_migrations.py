"""Tests for idempotent SQLite schema migration."""

import sqlite3
from contextlib import closing
from pathlib import Path

from app.storage.migrations import apply_migrations


def test_apply_migrations_creates_the_core_schema_once(tmp_path: Path) -> None:
    """The schema is complete and reapplying migrations does not duplicate rows."""

    database_path = tmp_path / "data" / "database.sqlite"
    apply_migrations(database_path)
    apply_migrations(database_path)

    with closing(sqlite3.connect(database_path)) as connection:
        applied = connection.execute("SELECT version FROM schema_migrations").fetchall()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert applied == [(1,)]
    assert {"runs", "artifacts", "analytics", "provider_health"}.issubset(tables)
