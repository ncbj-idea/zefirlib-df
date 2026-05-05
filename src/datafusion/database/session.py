import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema

from datafusion.database.db_settings import db_settings

_engine = create_engine(db_settings.connection_string)
_session_maker = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
_logger = logging.getLogger(__name__)


def get_engine() -> Engine:
    return _engine


def get_session() -> Iterator[Session]:
    global _session_maker
    session = _session_maker()
    try:
        yield session
    finally:
        session.close()


def create_schema_if_not_exists(schema: str, engine: Engine) -> None:
    inspector = inspect(engine)
    if schema not in inspector.get_schema_names():
        try:
            with engine.connect() as conn:
                conn.execute(CreateSchema(schema))
        except SQLAlchemyError as error_msg:
            _logger.warning(error_msg)


class SessionContext:
    def __init__(self, db_engine: Engine | None = None, expire_on_commit: bool = False):
        if db_engine is not None:
            session_maker = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=db_engine,
                expire_on_commit=expire_on_commit,
            )
            self._session = session_maker()
        else:
            global _session_maker
            self._session = _session_maker()

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._session.close()
