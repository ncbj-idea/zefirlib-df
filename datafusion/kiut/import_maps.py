import logging

import geopandas as gpd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from urllib3.exceptions import ProtocolError

from datafusion.configs.kiut_config import WMSConfig
from datafusion.database.models.administrative_boundary import AdministrativeBoundary
from datafusion.database.models.map import Map
from datafusion.database.session import SessionContext
from datafusion.utils.crud import get_kiut_layer_by_name
from datafusion.utils.wms import WebMapServiceBulk

logger = logging.getLogger(__name__)

_adm_geom_col = AdministrativeBoundary.geom.name
_adm_tablename = AdministrativeBoundary.__tablename__

SELECT_GRID_STM = text(
    f"""
    WITH grid AS (
        SELECT (ST_SquareGrid(:bbox_size, ST_Extent({_adm_geom_col}))).*
        FROM {_adm_tablename}
        WHERE terc = :terc
    )
    SELECT ST_AsText({_adm_geom_col}), grid.*, ST_XMin({_adm_geom_col}) as xmin,
        ST_XMax({_adm_geom_col}) as xmax, ST_YMin({_adm_geom_col}) as ymin,
        ST_YMax({_adm_geom_col}) as ymax
    FROM grid
    """
)


def import_maps(
    db_engine: Engine,
    layer_name: str,
    import_id: int,
    terc: str,
    wms_params: WMSConfig,
) -> None:
    """
    Function for importing maps from WMS service

    Args:
        db_engine: (Engine) SQLAlchemy engine instance
        layer_name (str): Layer name
        import_id (int): import id
        terc (str):
        wms_params (WMSConfig): WMSCofnig instance
    """
    layer = get_kiut_layer_by_name(db_engine, layer_name)
    with SessionContext(db_engine) as db:
        df = gpd.GeoDataFrame.from_postgis(
            sql=SELECT_GRID_STM,
            con=db.get_bind(),
            params={
                "terc": terc,
                "bbox_size": wms_params.bbox_size,
            },
        )

        wmsb = WebMapServiceBulk(
            wms_params.url,
            version=wms_params.version,
        )

        bboxes = df[["xmin", "ymin", "xmax", "ymax"]].values.tolist()
        try:
            res = wmsb.getmaps(
                bboxes=bboxes,
                layers=[layer.name],
                size=(wms_params.image_size, wms_params.image_size),
                srs=f"EPSG:{wms_params.srid}",
                format="image/png",
            )
        except (ConnectionError, ProtocolError) as e:
            logger.error("WMS service connection error: %s", str(e))
            raise

        res = list(res)

        df["image"] = [el.get("image", None) for el in res]
        df["url"] = [el.get("url", None) for el in res]
        df["error"] = [el.get("error", None) for el in res]

        for it, row in enumerate(df.itertuples()):
            logger.debug("Inserting %d", it)
            image = row.image if not row.error else None
            g = Map(
                geom=row.geom.wkt,
                image=image,
                url=row.url,
                layer=layer.id,
                terc=terc,
                import_id=import_id,
            )
            db.add(g)
            db.flush()
        db.commit()
