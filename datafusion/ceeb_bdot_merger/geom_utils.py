"""Geometry-related helpers for BDOT processing.

Contains WKT parsing, centroid extraction, and coordinate transformation
helpers used by H3 indexing and spatial merging routines.
"""

from __future__ import annotations

import logging

import pandas as pd
from pyproj import Transformer
from shapely import wkt
from shapely.geometry import Point
from shapely.ops import unary_union

logger = logging.getLogger(__name__)


def _safe_wkt_parse(wkt_str: str) -> Point | None:
    """Safely parse a WKT string to a geometry object."""
    if not isinstance(wkt_str, str) or not wkt_str:
        return None
    try:
        return wkt.loads(wkt_str)
    except Exception as e:
        logger.debug(f"Failed to parse WKT: {str(e)[:100]}")
        return None


def _parse_wkt_centroid_series(geom_wkt: pd.Series) -> list[Point]:
    """Parse WKT geometry strings and extract centroids.

    Returns a list of centroid Point objects. Invalid geometries are
    replaced with None. Raises no exceptions but logs when many failures
    occur.
    """
    geoms = []
    error_count = 0
    non_empty_count = 0

    for idx, txt in enumerate(geom_wkt.fillna("")):
        if not txt or txt == "":
            geoms.append(None)
            continue

        non_empty_count += 1
        try:
            g = wkt.loads(txt)
            c = g.centroid
            geoms.append(c)
        except Exception as e:
            error_count += 1
            if error_count <= 5:  # Log first 5 errors in detail
                logger.debug(f"Failed to parse WKT geometry at index {idx}: {str(e)[:100]}")
            geoms.append(None)

    if error_count > 0:
        failure_rate = error_count / non_empty_count if non_empty_count > 0 else 0
        logger.warning(
            f"Failed to parse {error_count}/{non_empty_count} WKT geometries "
            f"({failure_rate:.1%}). These will be treated as missing values."
        )

        if failure_rate > 0.8 and non_empty_count > 0:
            from .exceptions import GeometryError

            raise GeometryError(
                f"Geometry parsing failure rate too high: {failure_rate:.1%} "
                f"({error_count}/{non_empty_count} failed). Check WKT geometry format in input data."
            )

    return geoms


def _transform_points(points: list[Point], from_crs: str, to_crs: str) -> list[Point]:
    """Transform Point geometries from one coordinate system to another."""
    try:
        transformer = Transformer.from_crs(from_crs, to_crs, always_xy=True)
    except Exception as e:
        from .exceptions import GeometryError

        raise GeometryError(f"Failed to create coordinate transformer from {from_crs} to {to_crs}: {e}") from e

    out: list[Point] = []
    for p in points:
        if p is None:
            out.append(None)
            continue
        try:
            x, y = transformer.transform(p.x, p.y)
            out.append(Point(x, y))
        except Exception as e:
            logger.debug(f"Failed to transform point ({p.x}, {p.y}): {e}")
            out.append(None)
    return out


def _merge_building_geometries_and_attributes(
    group: pd.DataFrame,
    id_col: str,
    geom_col: str,
    addr_distance_col: str,
    addr_vars: list[str],
    aggr_vars: list[str],
    bin_vars: list[str],
) -> pd.DataFrame:
    """Merge multiple building records into a single record.

    Combines geometries using unary_union and aggregates attributes according
    to their type (address, aggregatable, or binary).
    """
    from .helpers import _to_bool_series

    # Find address building (closest to address point)
    row_addr_idx = group[addr_distance_col].astype(float).idxmin()
    addr_row = group.loc[row_addr_idx]

    # Parse and merge geometries
    geoms = group[geom_col].apply(_safe_wkt_parse)
    geom_union = unary_union([g for g in geoms if g is not None])

    # Build merged record
    new_row = {}
    new_row["merged_id"] = "_".join(group[id_col].astype(str).tolist())
    new_row[id_col] = addr_row[id_col]

    # Address-based columns
    for col in addr_vars:
        new_row[col] = addr_row[col]

    # Aggregatable columns
    for col in aggr_vars:
        new_row[col] = group[col].sum()

    # Binary columns
    for col in bin_vars:
        new_row[col] = bool(_to_bool_series(group[col]).any())

    new_row["status"] = "to_join"
    new_row[geom_col] = geom_union.wkt if geom_union is not None else addr_row.get(geom_col)

    return pd.DataFrame([new_row])


__all__ = [
    "_safe_wkt_parse",
    "_parse_wkt_centroid_series",
    "_transform_points",
    "_merge_building_geometries_and_attributes",
]
