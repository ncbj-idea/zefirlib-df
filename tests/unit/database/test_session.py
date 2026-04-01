from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from datafusion.database.db_settings import DBSettings
from datafusion.database.session import create_schema_if_not_exists
from tests.conftest import get_test_engine


@contextmanager
def ensure_clean_schema(engine: Engine, schema_name: str) -> Generator[None, Any, None]:
    with engine.connect() as connection:
        if schema_name in inspect(engine).get_schema_names():
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
    try:
        yield
    finally:
        with engine.connect() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name}"))


def test_create_schema_if_not_exist(mock_database_settings: DBSettings) -> None:
    schema_name = "test_schema"
    engine = get_test_engine(mock_database_settings)

    with ensure_clean_schema(engine, schema_name):
        assert schema_name not in inspect(engine).get_schema_names()
        create_schema_if_not_exists(schema_name, engine)
        assert schema_name in inspect(engine).get_schema_names()
