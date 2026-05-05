from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.engine import Engine

from datafusion.database.session import SessionContext


class BBOX(NamedTuple):
    """Bounding box coordinates for spatial filtering.

    Attributes:
        minx: Minimum X coordinate (west)
        miny: Minimum Y coordinate (south)
        maxx: Maximum X coordinate (east)
        maxy: Maximum Y coordinate (north)
        srid: Spatial reference system ID
    """

    minx: float
    miny: float
    maxx: float
    maxy: float
    srid: int

    def to_string(self) -> str:
        """Convert BBOX to WFS string format: "minx,miny,maxx,maxy,srsname"."""
        srsname = f"urn:ogc:def:crs:EPSG::{self.srid}"
        return f"{self.minx},{self.miny},{self.maxx},{self.maxy},{srsname}"

    def to_tuple(self) -> tuple[float, float, float, float, str]:
        """Convert BBOX to OWSLib tuple format: (minx, miny, maxx, maxy, srsname)."""
        srsname = f"urn:ogc:def:crs:EPSG::{self.srid}"
        return (self.minx, self.miny, self.maxx, self.maxy, srsname)

    def __str__(self) -> str:
        """String representation for logging."""
        return self.to_string()


def get_wfs_bbox(db_engine: Engine, terc: str, srid: int = 2180) -> BBOX | None:
    """Generate BBOX for WFS requests based on TERC code.

    Queries the administrative_boundary table to get the geometry bounds
    for the specified TERC code and returns a BBOX object.

    Args:
        db_engine: Database engine for querying administrative boundaries
        terc: TERC code for the administrative unit
        srid: Spatial reference system ID (default: 2180)

    Returns:
        BBOX object with coordinates and SRID, or None if not found
    """
    try:
        with SessionContext(db_engine) as session:
            # Query the boundary geometry and extract bbox coordinates in a single query
            query = text("""
                SELECT
                    ST_XMin(ST_Envelope(geom)) as minx,
                    ST_YMin(ST_Envelope(geom)) as miny,
                    ST_XMax(ST_Envelope(geom)) as maxx,
                    ST_YMax(ST_Envelope(geom)) as maxy
                FROM administrative_boundary
                WHERE terc = :terc
                ORDER BY import_id DESC
                LIMIT 1
            """)

            result = session.execute(query, {"terc": terc}).fetchone()

            if result and result.minx is not None:
                return BBOX(
                    minx=float(result.minx),
                    miny=float(result.miny),
                    maxx=float(result.maxx),
                    maxy=float(result.maxy),
                    srid=srid,
                )

    except Exception as e:
        # Log error but don't fail - fall back to no bbox filtering
        print(f"Warning: Failed to get BBOX for TERC {terc}: {e}")

    return None


def get_wfs_bbox_tuple(db_engine: Engine, terc: str, srid: int = 2180) -> tuple[float, float, float, float, str] | None:
    """Get BBOX as tuple for OWSLib compatibility.

    Returns BBOX in format: (minx, miny, maxx, maxy, srsname)

    Args:
        db_engine: Database engine for querying administrative boundaries
        terc: TERC code for the administrative unit
        srid: Spatial reference system ID (default: 2180)

    Returns:
        BBOX tuple or None if not found
    """
    bbox = get_wfs_bbox(db_engine, terc, srid)
    return bbox.to_tuple() if bbox else None
