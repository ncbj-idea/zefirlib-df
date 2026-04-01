import logging
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from datafusion.configs.kiut_config import KIUTConfig
from datafusion.database.models.kiut_layer import KIUTLayer
from datafusion.database.models.terc import Terc
from datafusion.database.session import SessionContext
from datafusion.kiut.layers import AllowedLayerNames
from datafusion.teryt_codes.teryt_codes import import_terc_codes
from datafusion.utils.crud import get_kiut_layer_name_to_id_dict

logger = logging.getLogger(__name__)


def _add_kiut_layers(db: Session) -> None:
    layers_in_db = get_kiut_layer_name_to_id_dict(db)
    for id_, layer in enumerate(AllowedLayerNames, 1):
        layername = layer.value
        if layername not in layers_in_db:
            obj = KIUTLayer(id=id_, name=layername)
            db.add(obj)
    db.commit()


def _add_terc_codes(db: Session, kiut_config: KIUTConfig) -> None:
    if not db.query(Terc).first():
        import_terc_codes(db, Path(kiut_config.terc_urzedowy_xml_path))


def initialize_kiut_util_database(db_engine: Engine, kiut_config: KIUTConfig) -> None:
    logger.info("Initializing KIUT util database")
    with SessionContext(db_engine) as db:
        _add_kiut_layers(db)
        _add_terc_codes(db, kiut_config)
