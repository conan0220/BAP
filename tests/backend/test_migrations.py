from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect


def test_initial_migration_contains_only_prototype_tables(tmp_path, monkeypatch) -> None:
    database = tmp_path / "migration.db"
    monkeypatch.setenv("BAP_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    from sqlalchemy import create_engine

    tables = set(inspect(create_engine(f"sqlite:///{database.as_posix()}")).get_table_names())
    assert tables == {"alembic_version", "app_releases", "refresh_sessions", "users"}
    command.downgrade(config, "base")
