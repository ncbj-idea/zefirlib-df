import logging
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO
from zipfile import ZipFile

import requests
from sqlalchemy import Table, bindparam, column, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm.session import Session

from datafusion.configs.bdot_config import BDOTConfig
from datafusion.database.db_settings import DBSettings
from datafusion.database.models.base_class import Base
from datafusion.database.models.bdot import BDOT10k
from datafusion.database.session import SessionContext
from datafusion.readers.base_reader import Reader
from datafusion.utils.ogr import OgrCaller
from datafusion.utils.sql import build_insert, build_json_column

_logger = logging.getLogger(__name__)


class BDOTReader(Reader):
    """
    Class for handling importing data from BDOT to the database.
    """

    def __init__(
        self,
        config: BDOTConfig,
        engine: Engine,
        db_settings: DBSettings,
    ) -> None:
        """
        Constructor of BDOTReader.
        Args:
            config (BDOTConfig): BDOTConfig object
            engine (engine): Engine object:
            db_settings (DBSettings): DBSettings object:
        """
        self.config = config
        self.db_settings = db_settings
        self.engine = engine

    def run(self) -> None:
        """
        Function for importing data from BDOT to the database.
        """
        _logger.info("Running BDOT reader")
        _logger.info("Getting meta data")
        meta_obj = self.get_meta_obj(
            table_name=BDOT10k.__tablename__,
            config=self.config,
            engine=self.engine,
        )
        full_table_name = f"{self.config.tmp_table_schema}.{self.config.tmp_table_name}"
        _logger.info("Getting raw BDOT data")
        self._get_raw_bdot_data(table_name=full_table_name)
        with SessionContext(self.engine) as session:
            raw_table = Table(
                self.config.tmp_table_name,
                Base.metadata,
                autoload_with=session.bind,
                schema=self.config.tmp_table_schema,
            )
            _logger.info("Appending BDOT table")
            self._append_bdot_table(
                session,
                meta_obj.id,
                raw_table,
            )
            session.commit()

    def _append_bdot_table(
        self,
        session: Session,
        import_id: int,
        raw_table: Table,
    ):
        _logger.debug("Appending bdot data")
        jsonized_cols = [
            column(col.name)
            for col in raw_table.columns
            if col.name != self.config.geom_col_name and col.name not in self.config.source_column_map
        ]

        geom = column(self.config.geom_col_name)
        raw_geom = func.ST_AsEWKT(geom).label(BDOT10k.geom.name)
        jsonized_cols.append(raw_geom)

        placeholder = "import_id"
        columns = [
            bindparam(placeholder).label(BDOT10k.import_id.name),
            geom.label(BDOT10k.geom.name),
            build_json_column(jsonized_cols).label(BDOT10k.other.name),
        ]
        columns.extend([column(col).label(label) for col, label in self.config.source_column_map.items()])
        _logger.debug("Inserting bdot data")
        ins = build_insert(columns=columns, source=raw_table, destination=BDOT10k.__table__)
        session.execute(ins, {placeholder: import_id})

    def _fetch_layer(self, content: BinaryIO, tmp_dir: Path) -> Path | None:
        _logger.info("Fetching layer from %s", tmp_dir)
        with ZipFile(content) as _zip:
            building_xmls = [file for file in _zip.infolist() if self.config.layer_name in file.filename]
            if len(building_xmls) != 1:
                raise ValueError(f"Layer name {self.config.layer_name} not found config")
            # TODO: Print all available layers in xml
            building_xml = building_xmls[0]
            filepath = _zip.extract(building_xml.filename, path=tmp_dir)
        return Path(filepath)

    def _get_raw_bdot_data(self, table_name: str):
        _logger.info("Getting raw BDOT data %s", table_name)
        with TemporaryDirectory() as tmp_dir:
            _logger.debug("Using temporary directory: %s", tmp_dir)
            content = BytesIO(self.read(self.config.url))
            layer = self._fetch_layer(content, Path(tmp_dir))
            OgrCaller(
                table_name=table_name,
                layer_name=self.config.layer_name,
            )(layer, self.db_settings)

    @staticmethod
    def read(url: str) -> bytes:
        _logger.info("Reading from %s", url)
        response = requests.get(url)
        return response.content
