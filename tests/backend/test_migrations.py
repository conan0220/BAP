from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect


def test_migrations_create_and_remove_all_current_tables(tmp_path, monkeypatch) -> None:
    database = tmp_path / "migration.db"
    monkeypatch.setenv("BAP_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    from sqlalchemy import create_engine

    tables = set(inspect(create_engine(f"sqlite:///{database.as_posix()}")).get_table_names())
    assert tables == {
        "alembic_version",
        "analysis_input_bindings",
        "analysis_jobs",
        "analysis_results",
        "app_releases",
        "imu_csv_files",
        "measurement_sessions",
        "refresh_sessions",
        "users",
    }
    columns = {
        item["name"]
        for item in inspect(create_engine(f"sqlite:///{database.as_posix()}")).get_columns(
            "measurement_sessions"
        )
    }
    assert {
        "requested_duration_seconds",
        "actual_duration_seconds",
        "stop_reason",
    } <= columns
    command.downgrade(config, "base")
    assert set(inspect(create_engine(f"sqlite:///{database.as_posix()}")).get_table_names()) == {
        "alembic_version"
    }
