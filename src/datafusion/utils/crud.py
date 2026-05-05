from __future__ import annotations

import logging
from typing import Any

from pandas import DataFrame, read_sql
from sqlalchemy import MetaData, Table
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoSuchTableError, SQLAlchemyError
from sqlalchemy.orm import Session

from datafusion.database.models.import_metadata import ImportMetadata
from datafusion.database.models.kiut_layer import KIUTLayer
from datafusion.database.models.mapping_import_to_terc import MappingImportToTerc
from datafusion.database.session import SessionContext

_logger = logging.getLogger(__name__)

metadata = MetaData()


def create_import_metadata(db_engine: Engine, table_name: str, metadata: dict[str, Any]) -> ImportMetadata:
    try:
        with SessionContext(db_engine) as session:
            obj = ImportMetadata(table_name=table_name, meta=metadata)
            session.add(obj)
            session.commit()
        return obj
    except SQLAlchemyError as e:
        # Handle case where table doesn't exist yet (first-time setup)
        if "does not exist" in str(e) or "UndefinedTable" in str(e):
            _logger.info(f"import_metadata table does not exist yet, cannot create metadata for {table_name}")
            return None
        raise


def create_import_to_terc_mapping(db_engine: Engine, import_id: int, terc: str) -> MappingImportToTerc:
    try:
        with SessionContext(db_engine) as session:
            obj = MappingImportToTerc(import_id=import_id, terc=terc)
            session.add(obj)
            session.commit()
            return obj
    except SQLAlchemyError as e:
        # Handle case where tables don't exist yet (first-time setup)
        if "does not exist" in str(e) or "UndefinedTable" in str(e):
            _logger.info(f"import_to_terc table does not exist yet, cannot create mapping for import_id {import_id}")
            return None
        raise


def get_kiut_layer_by_name(db_engine: Engine, layer_name: str) -> KIUTLayer:
    with SessionContext(db_engine) as session:
        obj = session.query(KIUTLayer).filter(KIUTLayer.name == layer_name).one()
        return obj


def get_process_state(process_name: str, terc: str, engine: Engine) -> dict | None:
    """Get process state from import_metadata table."""
    try:
        with SessionContext(engine) as session:
            meta = session.query(ImportMetadata).filter(ImportMetadata.table_name == f"{process_name}_{terc}").first()
            if meta and meta.meta:
                return meta.meta
            return None
    except SQLAlchemyError as e:
        # Handle case where table doesn't exist yet (first-time setup)
        if "does not exist" in str(e) or "UndefinedTable" in str(e):
            _logger.info(f"import_metadata table does not exist yet for {process_name}_{terc}, assuming first run")
            return None
        raise


def save_process_state(
    process_name: str,
    terc: str,
    step: int,
    status: str,
    engine: Engine,
) -> None:
    """Save process state to import_metadata table."""
    try:
        with SessionContext(engine) as session:
            meta = session.query(ImportMetadata).filter(ImportMetadata.table_name == f"{process_name}_{terc}").first()

            data = {"step": step, "status": status}

            if meta:
                meta.meta = data
            else:
                obj = ImportMetadata(table_name=f"{process_name}_{terc}", meta=data)
                session.add(obj)
            session.commit()
    except SQLAlchemyError as e:
        # Handle case where table doesn't exist yet (first-time setup)
        if "does not exist" in str(e) or "UndefinedTable" in str(e):
            _logger.info(f"import_metadata table does not exist yet for {process_name}_{terc}, cannot save state")
            return
        raise


def get_kiut_layer_name_to_id_dict(session: Session) -> dict[str, int]:
    return {obj.name: obj.id for obj in session.query(KIUTLayer).all()}


def load_dataframe_from_db(
    engine: Engine,
    table_name: str,
    columns: list[str] | None = None,
    chunk_size: int | None = None,
    allow_empty: bool = False,
) -> DataFrame:
    """
    Load a table from the database into a pandas DataFrame.

    Args:
        engine: SQLAlchemy engine for database connection.
        table_name: Name of the table to load.
        columns: Optional list of column names to load. If None, loads all columns.
        chunk_size: If specified, returns an iterator yielding DataFrames of this size.
        allow_empty: If True, allows loading empty tables without raising an error.

    Returns:
        DataFrame containing the table data.

    Raises:
        ValueError: If table_name is empty or contains invalid characters.
        RuntimeError: If table does not exist or is empty (when allow_empty=False).
        SQLAlchemyError: If database operation fails.
    """
    # Input validation
    if not table_name or not table_name.strip():
        raise ValueError("Table name cannot be empty")

    table_name = table_name.strip()

    try:
        # Load table metadata directly - this will raise NoSuchTableError if table doesn't exist
        table_obj = Table(table_name, metadata, autoload_with=engine)

        # Build query with optional column selection
        if columns:
            # Validate columns exist in table
            table_columns = {col.name for col in table_obj.columns}
            invalid_columns = set(columns) - table_columns
            if invalid_columns:
                raise ValueError(f"Invalid columns: {invalid_columns}. Available columns: {table_columns}")
            query = table_obj.select().with_only_columns(*[table_obj.c[col] for col in columns])
        else:
            query = table_obj.select()

        # Load data with proper error handling
        _logger.info(f"Loading table '{table_name}' from database")
        df = read_sql(query, engine, chunksize=chunk_size)

        # Handle empty table case
        if not allow_empty and (df.empty if chunk_size is None else False):
            raise RuntimeError(f"Table '{table_name}' is empty. Use allow_empty=True to load empty tables.")

        if chunk_size is None:
            _logger.info(f"Loaded {len(df)} rows from '{table_name}'")

        return df

    except NoSuchTableError as e:
        raise NoSuchTableError(f"Table '{table_name}' does not exist.") from e
    except SQLAlchemyError as e:
        _logger.error(f"Database error loading table '{table_name}': {e}")
        raise
    except Exception as e:
        _logger.error(f"Unexpected error loading table '{table_name}': {e}")
        raise


def save_dataframe_to_db(engine: Engine, df: DataFrame, table_name: str, if_exists="replace", chunk_size=10000):
    """
    Safely save DataFrame to database with error handling

    Args:
        engine: SQLAlchemy engine
        df: pandas DataFrame
        table_name: target table name
        if_exists: 'replace', 'append', or 'fail'
        chunk_size: number of rows per insert chunk
    """
    try:
        with engine.begin() as connection:  # Auto-commits on success, rolls back on error
            df.to_sql(
                table_name,
                connection,
                if_exists=if_exists,
                index=False,
                chunksize=chunk_size,
                method="multi",  # Faster for many rows
            )
        logging.info(f"Successfully saved {len(df)} rows to {table_name}")

    except SQLAlchemyError as e:
        logging.error(f"Database error: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise
    finally:
        engine.dispose()  # Clean up connection pool
