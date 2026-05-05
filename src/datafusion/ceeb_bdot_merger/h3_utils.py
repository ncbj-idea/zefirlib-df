"""H3 and related evaluation helpers.

Contains functions for computing H3 indices, neighbor lookups and Gini
calculation used by the evaluation pipeline.
"""

from __future__ import annotations

import logging
import math

import h3
import numpy as np
import pandas as pd

from .exceptions import H3ConversionError

logger = logging.getLogger(__name__)


def _validate_h3_resolution(resolution: int) -> None:
    if not (0 <= resolution <= 15):
        raise ValueError(f"H3 resolution must be between 0 and 15, got {resolution}")


def _compute_h3_from_geometries(geom_series: pd.Series, coord_system: str, h3_resolution: int) -> pd.Series:
    """Compute H3 index from WKT geometry series."""
    from .geom_utils import _parse_wkt_centroid_series, _transform_points

    # Parse and extract centroids
    centroids = _parse_wkt_centroid_series(geom_series)

    # Transform to EPSG:4326 for H3
    logger.debug(f"Transforming {len(centroids)} centroids from {coord_system} to EPSG:4326")
    centroids_ll = _transform_points(centroids, coord_system, "EPSG:4326")

    # Compute H3 indices
    h3_vals = []
    h3_error_count = 0

    for i, p in enumerate(centroids_ll):
        if p is None or math.isnan(p.x) or math.isnan(p.y):
            h3_vals.append(None)
            continue
        try:
            h3_vals.append(h3.latlng_to_cell(p.y, p.x, int(h3_resolution)))
        except Exception as e:
            h3_error_count += 1
            if h3_error_count <= 3:
                logger.warning(f"H3 conversion failed for point {i} ({p.y}, {p.x}): {e}")
            h3_vals.append(None)

    # Check for high failure rate
    if h3_error_count > 0:
        failure_rate = h3_error_count / len(h3_vals) if h3_vals else 0
        logger.warning(f"Failed to compute H3 index for {h3_error_count}/{len(h3_vals)} points ({failure_rate:.1%})")

        if failure_rate > 0.5:
            raise H3ConversionError(
                f"H3 conversion failure rate too high: {failure_rate:.1%} "
                f"({h3_error_count}/{len(h3_vals)} failed). Check coordinate system and H3 resolution settings."
            )

    return pd.Series(h3_vals, index=geom_series.index)


def _get_h3_ring_neighbors(h3_index: str, ring_size: int = 1, use_cache: bool = True) -> list[str]:
    if use_cache:
        cache_key = (h3_index, ring_size)
        if not hasattr(_get_h3_ring_neighbors, "_cache"):
            _get_h3_ring_neighbors._cache = {}

        if cache_key in _get_h3_ring_neighbors._cache:
            return _get_h3_ring_neighbors._cache[cache_key]

    try:
        result = list(h3.grid_ring(h3_index, ring_size))
        if use_cache and len(_get_h3_ring_neighbors._cache) < 10000:
            _get_h3_ring_neighbors._cache[cache_key] = result
        return result
    except Exception as e:
        logger.debug(f"Failed to get H3 ring for {h3_index}: {e}")
        return []


def _compute_min_grid_distance(h3_index: str, connected_set: set) -> int:
    if not isinstance(h3_index, str) or h3_index == "":
        return 0
    if not connected_set or len(connected_set) == 0:
        return 0
    try:
        return min(h3.grid_distance(h3_index, other) for other in connected_set)
    except Exception as e:
        logger.debug(f"Failed to compute grid distance for {h3_index}: {e}")
        return 0


def _compute_median_neighbor_value(h3_index: str, value_map: dict[str, float], ring_size: int = 1) -> float:
    neighbors = _get_h3_ring_neighbors(h3_index, ring_size) if isinstance(h3_index, str) else []
    vals = [value_map.get(n) for n in neighbors if n in value_map]
    vals = [v for v in vals if v is not None and not math.isnan(v)]
    return float(pd.Series(vals).median()) if vals else float("nan")


def _calculate_gini_coefficient(values: pd.Series) -> float:
    x = values.astype(float).to_numpy()
    x = x[x >= 0]
    if x.size == 0:
        return 0.0
    x_sorted = np.sort(x)
    cumx = x_sorted.cumsum()
    lorenz = np.insert(cumx / (cumx[-1] if cumx[-1] != 0 else 1.0), 0, 0)
    p = np.linspace(0, 1, lorenz.size)
    auc = np.trapz(lorenz, p)
    return float(1 - 2 * auc)


__all__ = [
    "_validate_h3_resolution",
    "_compute_h3_from_geometries",
    "_get_h3_ring_neighbors",
    "_compute_min_grid_distance",
    "_compute_median_neighbor_value",
    "_calculate_gini_coefficient",
]
