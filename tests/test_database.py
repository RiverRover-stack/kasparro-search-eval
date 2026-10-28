from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import inspect

from backend.app.database import build_engine, initialize_database


ROOT = Path(__file__).resolve().parents[1]


def test_initialize_database_adds_attempt_metadata_to_existing_sqlite_schema() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        database_path = Path(directory) / "migration.db"
        engine = build_engine(f"sqlite:///{database_path.as_posix()}")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE model_attempts (id INTEGER PRIMARY KEY, validation_error TEXT)"
            )

        initialize_database(engine)
        initialize_database(engine)

        columns = {column["name"] for column in inspect(engine).get_columns("model_attempts")}
        assert "provider_metadata" in columns
        engine.dispose()
