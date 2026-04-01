import logging

from sqlalchemy import Column, Table, column, func, select, text
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.engine import Engine
from sqlalchemy.sql.elements import Label

from datafusion.database.session import SessionContext

_logger = logging.getLogger(__name__)


def build_json_column(
    jsonized_columns: list[Column],
) -> Label:
    tmp_alias = "d"
    json_ = func.json_strip_nulls(
        func.row_to_json(
            select(column(tmp_alias)).select_from(select(*jsonized_columns).alias(tmp_alias)).scalar_subquery()
        )
    )
    return json_


def build_insert(columns: list[Column], source: Table, destination: Table) -> Insert:
    sel = select(columns).select_from(source)
    ins = destination.insert().from_select(sel.subquery().columns, sel)
    return ins


def create_procedure(db_engine: Engine, procedure: str) -> None:
    with SessionContext(db_engine) as db:
        db.execute(procedure)
        db.commit()


def call_procedure(db_engine: Engine, procedure_name: str, *parameters) -> None:
    with SessionContext(db_engine) as db:
        binded_params = {f"param{i}": value for i, value in enumerate(parameters)}
        placeholders = ", ".join(f":{k}" for k in binded_params.keys())
        sanitized_procedure_name = str(column(procedure_name))
        stm = f"CALL {sanitized_procedure_name}({placeholders})"
        db.execute(text(stm), binded_params)
        _logger.debug("Calling: `%s` with params: %s", stm, binded_params)
        db.commit()
