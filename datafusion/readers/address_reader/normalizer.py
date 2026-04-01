"""
Normalizer for Address Reader.

This module provides the AddressNormalizer class for extracting JSON fields into separate columns.
"""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from datafusion.database.session import SessionContext

_logger = logging.getLogger(__name__)


class AddressNormalizer:
    """
    Normalizer for address point data.
    """

    def __init__(self, db_engine: Engine) -> None:
        self.db_engine = db_engine

    def normalize(self, import_id: int) -> None:
        """
        Normalize address data by extracting JSON fields into separate columns.
        """
        update_sql = text("""
            UPDATE address_point
            SET miejscowosc = other ->> 'miejscowosc',
                kod_pocztowy = other ->> 'kod',
                ulica = other ->> 'ulica',
                numer_porzadkowy = other ->> 'numer'
            WHERE address_point.import_id = :import_id
        """)
        _logger.debug("Normalizing address data for import_id=%d", import_id)
        with SessionContext(self.db_engine) as db:
            db.execute(update_sql, {"import_id": import_id})
            db.commit()
        _logger.debug("Address data normalization completed for import_id=%d", import_id)
