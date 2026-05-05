import io
import logging
from typing import Any

import numpy as np
from geoalchemy2.shape import from_shape
from PIL import Image
from sqlalchemy.engine import Engine, RowMapping

from datafusion.database.models.map import Map
from datafusion.database.models.tile import Tile
from datafusion.database.session import SessionContext
from datafusion.kiut.array_slicer import ArraySlicer
from datafusion.kiut.geomap_array import GeomapRGBAArray
from datafusion.kiut.map_analyze.layer_checkers.interface import LayerChecker
from datafusion.utils.crud import get_kiut_layer_name_to_id_dict
from datafusion.utils.image.color import is_background
from datafusion.utils.image.serialize import image_to_bytes
from datafusion.utils.typings import LayernameToId_DictT

_logger = logging.getLogger(__name__)


def _is_blank(arr: np.ndarray) -> bool:
    return is_background(arr).all()


Mapping_Type = list[dict[str, Any]]


def _process_map(
    map_data: RowMapping,
    checker: LayerChecker,
    slicer: ArraySlicer,
    layername2id: LayernameToId_DictT,
    srid: int,
) -> Mapping_Type | None:
    map_id = map_data["id"]
    if not map_id or map_data["image"] is None:
        _logger.debug("Process map %d has empty or invalid image. Skipped.", map_id)
        return None
    try:
        image = Image.open(io.BytesIO(map_data["image"]))
        image = image.convert("RGBA")
    except Exception:
        _logger.debug("Process map %d has empty or invalid image. Skipped.", map_id)
        return None
    list_of_mappings = []  # type: ignore
    arr = np.array(image)
    # If the whole map is blank, then all tiles are also blank
    if _is_blank(arr):
        _logger.debug("Process map %d is empty. Skipped.", map_id)
        return list_of_mappings
    geoarray = GeomapRGBAArray(
        arr,
        min_x=map_data["xmin"],
        max_x=map_data["xmax"],
        min_y=map_data["ymin"],
        max_y=map_data["ymax"],
    )

    tiles_data = slicer.to_tiles(geoarray)
    _logger.debug("Map %d is split to %d tiles", map_id, len(tiles_data))

    for tile, debug_data in tiles_data:
        existing_layers = checker.get_existing_layers(tile.array)

        for layer in existing_layers:
            mapping = {
                "map_id": map_id,
                "geom": from_shape(tile.get_geom(), srid=srid),
                "layer": layername2id[layer],
                "debug": debug_data,
                "image": image_to_bytes(tile.get_image()),
            }
            list_of_mappings.append(mapping)
    _logger.debug("Process map %d finished", map_id)
    return list_of_mappings


def import_tiles(
    db_engine: Engine,
    import_id: int,
    checker: LayerChecker,
    slicer: ArraySlicer,
    srid: int,
) -> None:
    """
    Function for importing and analyzing KiUT tiles into the database
    Args:
        db_engine (Engine): Sqlalchemy engine instance
        import_id (int): Import ID based on metadata
        checker (LayerChecker): Instance of LayerChecker
        slicer(ArraySlicer): Instance of ArraySlicer:
        srid (int): srid used in POSTGIS geometry:

    """
    stm = f"""
        SELECT map.*,
               ST_XMin(geom) as xmin,
               ST_XMax(geom) as xmax,
               ST_YMin(geom) as ymin,
               ST_YMax(geom) as ymax
        FROM {Map.__tablename__} as map
        WHERE import_id = '{import_id}'
    """
    with SessionContext(db_engine) as db:
        maps = db.execute(stm).mappings().all()
        layername2id = get_kiut_layer_name_to_id_dict(db)
        error_count, maps_number = 0, len(maps)
        _logger.info("Fetched %d maps from table maps", maps_number)
        for map_data in maps:
            try:
                list_of_mappings = _process_map(map_data, checker, slicer, layername2id, srid)
                if list_of_mappings is not None:
                    db.bulk_insert_mappings(mapper=Tile, mappings=list_of_mappings)
            except Exception:
                map_id = map_data["id"]
                _logger.exception("Error when process map %d.", map_id)
                error_count += 1
                continue
        _logger.info("Processed with success %d maps. With errors %d.", maps_number, error_count)

        db.commit()
