from abc import ABC, abstractmethod
from pathlib import Path

from sqlalchemy.engine import Engine

from datafusion.configs.bdot_config import BDOTConfig
from datafusion.configs.ceeb_config import CEEBConfig
from datafusion.configs.kiut_config import KIUTConfig
from datafusion.configs.pvgis_config import PVGISConfig
from datafusion.database.models.import_metadata import ImportMetadata
from datafusion.database.session import create_schema_if_not_exists
from datafusion.utils.crud import create_import_metadata

_ALLOWED_CONFIGS_T = BDOTConfig | CEEBConfig | KIUTConfig | PVGISConfig


class Reader(ABC):
    """
    Abstract class for data reader class.
    """

    @abstractmethod
    def run(self) -> None:
        """
        Abstract method for running reader.
        """
        pass

    @staticmethod
    def get_meta_obj(
        table_name: str,
        config: _ALLOWED_CONFIGS_T,
        engine: Engine,
        use_tmp_schema: bool = True,
    ) -> ImportMetadata:
        """
        Function creates entry in meta data table.
        Args:
            table_name (str): Table name.
            config: Config object
            engine (sqlalchemy.engine.Engine): Engine object.
            use_tmp_schema (bool): Use tmp schema when reading from database.

        Returns:

        """
        meta_obj = create_import_metadata(
            db_engine=engine,
            table_name=table_name,
            metadata={"config": dict(config)},
        )
        if use_tmp_schema:
            create_schema_if_not_exists(schema=config.tmp_table_schema, engine=engine)
        return meta_obj

    @staticmethod
    def _cast_all_paths_to_str(
        config: BDOTConfig | CEEBConfig,
    ) -> BDOTConfig | CEEBConfig:
        for k, v in config.__dict__.items():
            if isinstance(v, Path):
                setattr(config, k, str(v))
        return config
