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
from datafusion.configs.borders_config import BordersConfig
from datafusion.database.db_settings import DBSettings
from datafusion.database.models.address_point import AddressPoint
from datafusion.database.models.base_class import Base
from datafusion.database.session import SessionContext
from datafusion.readers.address_reader.normalizer import AddressNormalizer
from datafusion.readers.address_reader.repository import AddressRepository
from datafusion.readers.address_reader.wfs_client import AddressWfsClient
from datafusion.readers.base_reader import Reader
from datafusion.readers.borders_reader import BordersReader
from datafusion.utils.ogr import OgrCaller
from datafusion.utils.spatial import get_wfs_bbox

_logger = logging.getLogger(__name__)

# Constants
_GML_FILENAME_TEMPLATE = "address_points_page_{page_number:03d}.gml"


class AddressReader(Reader):
    """
    Class for reading addresses from Geoportal.

    The aim of this class is to parse the open data from Geoportal and
    import it into the database. It uses WFS (Web Feature Service) to fetch
    address point data and imports it into a PostGIS database.
    """

    def __init__(
        self,
        config: AddressConfig,
        db_engine: Engine,
        db_settings: DBSettings,
        borders_config: BordersConfig | None = None,
    ) -> None:
        """
        Initialize AddressReader.
        """
        self.config = config
        self.borders_config = borders_config
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

                # A boundary is required for a safe, TERC-scoped BBOX query.
                self._ensure_administrative_boundary()

                # 1. Fetch data from WFS
                response_pages = self.wfs_client.fetch_data()

                # 2. Import to staging
                self._import_gml_pages_to_staging_table(response_pages)

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

                count = db.query(AddressPoint).filter(AddressPoint.import_id == meta_obj.id).count()
                if count == 0:
                    raise RuntimeError(
                        f"No address points were imported from PRG WFS ({self.config.url}, "
                        f"layer {self.config.layer_name}). Merge procedure will be impossible to perform."
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

    def _ensure_administrative_boundary(self) -> None:
        """Import missing borders before fetching addresses; never fall back to a nationwide query."""
        if get_wfs_bbox(self.db_engine, self.config.terc) is not None:
            return

        if self.borders_config is None:
            raise RuntimeError(
                f"No administrative boundary found for TERC {self.config.terc}. "
                "Import borders first (borders runner) or provide borders_config to import them automatically."
            )

        _logger.warning(
            "No administrative boundary found for TERC %s - importing borders first",
            self.config.terc,
        )
        BordersReader(
            config=self.borders_config,
            db_settings=self.db_settings,
            engine=self.db_engine,
        ).run()

        if get_wfs_bbox(self.db_engine, self.config.terc) is None:
            raise RuntimeError(
                f"Borders import for TERC {self.config.terc} produced no administrative boundary. "
                "Verify the TERC code and the borders WFS service configuration."
            )

    def _import_gml_pages_to_staging_table(self, response_pages: list[bytes]) -> None:
        """Replace staging with the first GML page, then append subsequent pages using OGR."""
        with TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            full_table_name = f"{self.config.tmp_table_schema}.{self.config.tmp_table_name}"
            _logger.info(
                "Importing %d GML page(s) to staging table '%s' (layer: '%s')",
                len(response_pages),
                full_table_name,
                self.config.layer_name,
            )

            for page_number, gml_content in enumerate(response_pages, start=1):
                gml_path = tmp_dir_path / _GML_FILENAME_TEMPLATE.format(page_number=page_number)
                _logger.debug("Saving WFS response page %d to temporary file: %s", page_number, gml_path)
                with open(gml_path, "wb") as gml_file:
                    gml_file.write(gml_content)

                ogr = OgrCaller(
                    table_name=full_table_name,
                    layer_name=self.config.layer_name,
                    layer_type="POINT",
                    replace=page_number == 1,
                    use_layer_name=False,
                )
                ogr(file=gml_path, db_settings=self.db_settings)
            _logger.info("Successfully imported address data to staging schema")
