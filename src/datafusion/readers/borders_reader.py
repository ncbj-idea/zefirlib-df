import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree.ElementTree import Element, SubElement, tostring

from owslib.wfs import WebFeatureService
from sqlalchemy import Table, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from datafusion.configs.borders_config import BordersConfig
from datafusion.database.db_settings import DBSettings
from datafusion.database.models.administrative_boundary import AdministrativeBoundary
from datafusion.database.models.base_class import Base
from datafusion.database.session import SessionContext
from datafusion.readers.base_reader import Reader
from datafusion.utils.ogr import OgrCaller

_logger = logging.getLogger(__name__)


class BordersReader(Reader):
    """
    Class for reading data from Państwowy Rejestr Granic to database.
    """

    def __init__(
        self,
        config: BordersConfig,
        db_settings: DBSettings,
        engine: Engine,
    ):
        """
        Constructor for BordersReader class.
        Args:
            config (BordersConfig): Borders configuration object.
            db_settings (DBSettings): Database settings object.
            session (Session): Database session object.
            engine (Engine): Database engine object.
        """
        self.config = config
        self.db_settings = db_settings
        self.engine = engine

    def run(self) -> None:
        """
        Function to run reading data from database.
        """
        _logger.info("Reading borders")
        self._import_gmina_borders()
        _logger.info("Finished reading borders")

    def _import_gmina_borders(self, remove_staging_table: bool = False) -> None:
        """
        This function is responsible for importing borders from Państwowy Rejestr Granic on the gmina level.
        Args:
            remove_staging_table (bool, optional): Flag to remove staging table from database. Defaults to False.
        """
        _logger.info("START")
        _logger.info("Process administrative boundaries.")
        _logger.debug("Creating metadata")
        meta_obj = self.get_meta_obj(
            table_name=AdministrativeBoundary.__tablename__,
            config=self.config,
            engine=self.engine,
        )

        with SessionContext(self.engine) as session:
            try:
                _logger.debug("Starting importing data for boundaries")
                self._import_raw_gminy_boundaries(
                    url=self.config.url,
                    table_name=self.config.tmp_table_name,
                    table_schema=self.config.tmp_table_schema,
                    tmp_dir_root=Path(self.config.tmp_dir_root),
                    layer_name=self.config.layer_name,
                    wfs_version=self.config.wfs_version,
                    timeout=self.config.timeout,
                    terc=self.config.terc,
                )
                raw_table = Table(
                    self.config.tmp_table_name,
                    Base.metadata,
                    autoload_with=session.bind,
                    schema=self.config.tmp_table_schema,
                )
                self._process_boundaries_normalization(session, raw_table, meta_obj.id)
                if remove_staging_table:
                    raw_table.drop(session.bind)
                session.commit()
                _logger.info("Administrative boundaries inserted to db")
            except Exception as e:
                _logger.error("Failed %s. Changes are rolled back", self.config.url)
                session.rollback()
                raise e

    def _import_raw_gminy_boundaries(
        self,
        url: str,
        table_name: str,
        table_schema: str,
        tmp_dir_root: Path,
        layer_name: str,
        wfs_version: str,
        timeout: int,
        terc: str | None = None,
    ) -> None:
        """
        This functino import raw data from Państwowy Rejestr Granic.
        Args:
            url (str): URL for the open data source
            table_name (str): Name of the table to which the data will be imported.
            table_schema (str): Name of the table to which the data will be imported.
            tmp_dir_root (str): Path to the temporary directory.
            layer_name (str): Name of the layer frow which the data will be imported.
            wfs_version (str): WFS version of the WFS service
            timeout (int): Timeout in seconds.
            terc (str | None): TERC code to filter by (e.g., "0207011").

        """
        _logger.info("Starting importing gmina boundaries")
        _logger.debug("WFS_version %s", wfs_version)
        wfs = WebFeatureService(url, version=wfs_version, timeout=timeout)
        if layer_name not in wfs.contents:
            raise KeyError(
                "No  %s (expected) layer in returned layers from WFS service",
                layer_name,
            )
        _logger.info("Sending WFS get feature request to %s", wfs.url)
        _logger.info("Timeout is set to %s s", timeout)
        _logger.info("Please be patient as it take time to handle the request")

        filter_xml = None
        if terc:
            filter_xml = self._build_terc_filter(terc)
            _logger.info("Filtering by TERC code: %s", terc)

        response = wfs.getfeature(typename=layer_name, filter=filter_xml)
        _logger.info("Received response from WFS service")
        with TemporaryDirectory(dir=tmp_dir_root) as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            gml_path = tmp_dir_path / "prg_adm_boundaries.gml"
            _logger.info("Saving response to %s", str(gml_path))
            with open(gml_path, "wb") as boundaries_gml:
                boundaries_gml.write(response.read())
            full_table_name = f"{table_schema}.{table_name}"
            _logger.info(
                "Saving data to database table_name %s layer_name %s",
                full_table_name,
                layer_name,
            )
            ogr = OgrCaller(table_name=full_table_name, layer_name=layer_name)
            ogr(gml_path, self.db_settings)
            _logger.debug("Finishing saving results to database")

    @staticmethod
    def _build_terc_filter(terc: str) -> str:
        """
        Build OGC Filter XML for filtering by TERC code.
        Args:
            terc (str): TERC code (e.g., "0207011")
        Returns:
            str: OGC Filter XML string
        """
        pattern = f"{terc[:6]}*{terc[6]}" if len(terc) >= 7 else f"{terc}*"

        filter_elem = Element("ogc:Filter", xmlns="http://www.opengis.net/ogc")
        filter_elem.set("xmlns:ogc", "http://www.opengis.net/ogc")

        prop_is_like = SubElement(filter_elem, "ogc:PropertyIsLike")
        prop_is_like.set("wildCard", "*")
        prop_is_like.set("singleChar", "#")
        prop_is_like.set("escapeChar", "\\")

        prop_name = SubElement(prop_is_like, "ogc:PropertyName")
        prop_name.text = "jpt_kod_je"

        literal = SubElement(prop_is_like, "ogc:Literal")
        literal.text = pattern

        return tostring(filter_elem, encoding="unicode")

    @staticmethod
    def _process_boundaries_normalization(db: Session, raw_table: Table, import_id: int) -> None:
        """
        This function performs boundaries normalization
        Args:
            db (Session): Database session object.
            raw_table (Table): Raw table to process.
            import_id (int): Id of the imported boundaries.
        """
        # fmt: off
        stm = select(
            text(
                ":import_id, left(jpt_kod_je, 6) || right(jpt_kod_je, 1) terc,"
                ' lower(jpt_nazwa_) as name, "msgeometry" as geom'
            )
        ).select_from(raw_table)
        # fmt: on
        columns = [
            AdministrativeBoundary.import_id.name,
            AdministrativeBoundary.terc.name,
            AdministrativeBoundary.name.name,
            AdministrativeBoundary.geom.name,
        ]

        ins = AdministrativeBoundary.__table__.insert().from_select(columns, stm)
        db.execute(ins, {"import_id": import_id})
        db.flush()
