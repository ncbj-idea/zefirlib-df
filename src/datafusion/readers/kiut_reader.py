import logging

from sqlalchemy.engine import Engine

from datafusion.configs.kiut_config import KIUTConfig
from datafusion.constants import CONFIG_KEY
from datafusion.database.models.map import Map
from datafusion.kiut.array_slicer import ArraySlicer
from datafusion.kiut.import_maps import import_maps
from datafusion.kiut.import_tiles import import_tiles
from datafusion.kiut.map_analyze.factory import get_grid_checker
from datafusion.readers.base_reader import Reader
from datafusion.utils.crud import create_import_metadata, create_import_to_terc_mapping

logger = logging.getLogger(__name__)

DEFAULT_LAYERS = ("przewod_cieplowniczy", "przewod_gazowy")


class KIUTReader(Reader):
    """
    A class used to read data from KIUT database.

    This class handles importing KIUT data to database, which includes
    importing information from geopartal and performs image processing of
    the desired layer.
    The results are saved to output database.
    """

    def __init__(
        self,
        config: KIUTConfig,
        engine: Engine,
    ) -> None:
        """
        Constructor for KIUTReader class.

        Args:
            config: KIUTConfig instance
            session: Sqlalchemy session instance
            engine: SQLAlchemy engine instance
        """
        self.config = config
        self.engine = engine

    def run(self) -> None:
        """
        Executed the KIUT reader import process
        """
        try:
            for layer in self.config.layers:
                layer_name = layer
                logger.info(
                    "(%s) Import: maps table (layer '%s')",
                    self.config.terc,
                    layer_name,
                )

                self._run(layer_name)

        except ValueError as e:
            logger.error(f"Wrong terc parameter: {e}")

    def _run(self, layer_name: str) -> None:
        """
        This function runs the KIUT reader process.
        Args:
            layer_name (str): layer name to import

        Returns:

        """
        logger.info(
            "(%s) Import: maps table (layer '%s')",
            self.config.terc,
            layer_name,
        )
        metadata = {
            "terc": self.config.terc,
            "layer_name": layer_name,
            CONFIG_KEY: self.config.model_dump(),
        }
        meta_obj = create_import_metadata(db_engine=self.engine, table_name=Map.__tablename__, metadata=metadata)
        create_import_to_terc_mapping(db_engine=self.engine, import_id=meta_obj.id, terc=self.config.terc)
        import_maps(
            db_engine=self.engine,
            layer_name=layer_name,
            terc=self.config.terc,
            import_id=meta_obj.id,
            wms_params=self.config.wms,
        )
        logger.info(
            "(%s) Import: tiles table. (layer '%s')",
            self.config.terc,
            layer_name,
        )
        polygonizer = get_grid_checker(layer_name, self.config.polygonization)
        slicer = ArraySlicer(self.config.number_of_slices_of_image_side)
        import_tiles(
            db_engine=self.engine,
            import_id=meta_obj.id,
            checker=polygonizer,
            slicer=slicer,
            srid=self.config.wms.srid,
        )
        logger.info("(%s)(%s) Finished.", meta_obj.id, self.config.terc)
