"""
Address Reader Module.

This module provides the AddressReader class for importing address point data
from Geoportal WFS services into a PostGIS database.
"""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import Table
from sqlalchemy.engine import Engine

from datafusion.configs.address_config import AddressConfig
from datafusion.database.db_settings import DBSettings
from datafusion.database.models.address_point import AddressPoint
from datafusion.database.models.base_class import Base
from datafusion.database.session import SessionContext
from datafusion.readers.address_reader.normalizer import AddressNormalizer
from datafusion.readers.address_reader.repository import AddressRepository
from datafusion.readers.address_reader.wfs_client import AddressWfsClient
from datafusion.readers.base_reader import Reader
from datafusion.utils.ogr import OgrCaller

_logger = logging.getLogger(__name__)

# Constants
_GML_FILENAME = "address_points.gml"


class AddressReader(Reader):
    """
    Class for reading addresses from Geoportal.

    The aim of this class is to parse the open data from Geoportal and
    import it into the database. It uses WFS (Web Feature Service) to fetch
    address point data and imports it into a PostGIS database.
    """

    def __init__(self, config: AddressConfig, db_engine: Engine, db_settings: DBSettings) -> None:
        """
        Initialize AddressReader.
        """
        self.config = config
        self.db_engine = db_engine
        self.db_settings = db_settings

        # Initialize components
        self.wfs_client = AddressWfsClient(config, db_engine)
        self.repository = AddressRepository()
        self.normalizer = AddressNormalizer(db_engine)

    def run(self) -> None:
        """
        Read data from Geoportal and write it to the database.
        """
        _logger.info("Reading addresses...")
        self._import_address_points()

    def _import_address_points(self) -> None:
        """
        Import address points to database and normalize them.
        """
        _logger.info(
            "Start processing address points from url %s using layer %s",
            self.config.url,
            self.config.layer_name,
        )
        import_id = self._import_address_data_to_db(remove_staging_table=False)
        _logger.info("Finished importing address points to db with import id %d", import_id)
        self.normalizer.normalize(import_id)
        _logger.info(
            "(%s) Completed processing address points for url '%s'.",
            import_id,
            self.config.url,
        )

    def _import_address_data_to_db(self, remove_staging_table: bool) -> int:
        """
        Import address points to database.
        """
        with SessionContext(self.db_engine) as db:
            try:
                meta_obj = self.get_meta_obj(
                    table_name=AddressPoint.__tablename__,
                    config=self.config,
                    engine=self.db_engine,
                )

                # 1. Fetch data from WFS
                response_content = self.wfs_client.fetch_data()

                # 2. Import to staging
                self._import_gml_to_staging_table(response_content)

                # 3. Move from staging to main table
                raw_table = Table(
                    self.config.tmp_table_name,
                    Base.metadata,
                    autoload_with=db.bind,
                    schema=self.config.tmp_table_schema,
                )
                self.repository.append_from_staging(
                    db=db,
                    import_id=meta_obj.id,
                    raw_table=raw_table,
                    geometry_column_name=self.config.geometry_column_name,
                )

                if remove_staging_table:
                    raw_table.drop(db.bind)

                db.commit()
                return meta_obj.id
            except Exception as e:
                _logger.error(
                    "Error while importing address points from %s (layer: %s). Changes are rolled back: %s",
                    self.config.url,
                    self.config.layer_name,
                    e,
                )
                db.rollback()
                if isinstance(e, (KeyError, ValueError, OSError)):
                    raise
                raise RuntimeError(f"Failed to import address points from {self.config.url}: {e}") from None

    def _import_gml_to_staging_table(self, gml_content: bytes) -> None:
        """
        Import GML content to staging table using OGR.
        """
        with TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            gml_path = tmp_dir_path / _GML_FILENAME

            _logger.debug("Saving WFS response to temporary file: %s", str(gml_path))
            with open(gml_path, "wb") as gml_file:
                gml_file.write(gml_content)
            _logger.debug("GML file saved successfully (%d bytes)", len(gml_content))

            full_table_name = f"{self.config.tmp_table_schema}.{self.config.tmp_table_name}"
            _logger.info(
                "Importing GML data to staging table '%s' (layer: '%s')",
                full_table_name,
                self.config.layer_name,
            )

            ogr = OgrCaller(
                table_name=full_table_name,
                layer_name=self.config.layer_name,
                layer_type="POINT",
                replace=True,
                use_layer_name=False,
            )
            ogr(file=gml_path, db_settings=self.db_settings)
            _logger.info("Successfully imported address data to staging schema")
