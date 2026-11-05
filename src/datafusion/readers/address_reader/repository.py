"""
Repository for Address Reader.

This module provides the AddressRepository class for database operations related to address points.
"""

import logging

from sqlalchemy import Table, bindparam, column, func
from sqlalchemy.orm.session import Session

from datafusion.database.models.address_point import AddressPoint
from datafusion.utils.sql import build_insert, build_json_column

_logger = logging.getLogger(__name__)

_IMPORT_ID_PLACEHOLDER = "import_id"
_EPSG_WGS84 = 4326


class AddressRepository:
    """
    Repository for address point database operations.
    """

    def append_from_staging(self, db: Session, import_id: int, raw_table: Table, geometry_column_name: str) -> None:
        """
        Append address points from staging table to main address_point table.
        """
        # Collect all non-geometry columns for JSON storage
        jsonized_cols = [column(col.name) for col in raw_table.columns if col.name != geometry_column_name]
        # Transform geometry to WGS84 and extract lat/lon for indexing
        geom = column(geometry_column_name)
        transformed_geom = func.ST_Transform(geom, _EPSG_WGS84)
        lat = func.ST_Y(transformed_geom).label("latitude")
        lon = func.ST_X(transformed_geom).label("longitude")

        placeholder = _IMPORT_ID_PLACEHOLDER
        columns = [
            bindparam(placeholder).label(AddressPoint.import_id.name),
            geom.label(AddressPoint.geom.name),
            build_json_column(jsonized_cols).label(AddressPoint.other.name),
            lat,
            lon,
        ]
        ins = build_insert(columns, raw_table, AddressPoint.__table__)
        _logger.debug("Stm: %s", ins)
        result = db.execute(ins, {placeholder: import_id})
        if result.rowcount == 0:
            raise ValueError(f"No address points inserted from staging table for import id {import_id}")
