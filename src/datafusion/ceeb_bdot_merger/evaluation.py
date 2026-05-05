"""Evaluation and synthetic index calculation helpers.

Contains functions for preparing H3-level evaluation metrics and computing the
synthetic index using several methods (average, volatility, distance, TOPSIS).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .constants import CONNECTIVITY_THRESHOLD, EPSILON, MIN_HEAT_DISTANCE
from .exceptions import ValidationError
from .h3_utils import _compute_median_neighbor_value, _compute_min_grid_distance

logger = logging.getLogger(__name__)


def _calculate_synthetic_index_average(data: np.ndarray) -> np.ndarray:
    z = (data - data.mean(axis=0)) / (data.std(axis=0, ddof=0) + EPSILON)
    return z.mean(axis=1)


def _calculate_synthetic_index_volatility(data: np.ndarray) -> np.ndarray:
    mean = data.mean(axis=0)
    sd = data.std(axis=0, ddof=0)
    vk = mean / (sd + EPSILON)
    vk = vk / (vk.sum() + EPSILON)
    z = (data - mean) / (sd + EPSILON)
    return (z @ vk.reshape(-1, 1)).ravel()


def _calculate_synthetic_index_distance(data: np.ndarray) -> np.ndarray:
    from scipy.spatial.distance import cdist

    z = (data - data.mean(axis=0)) / (data.std(axis=0, ddof=0) + EPSILON)
    pattern = z.max(axis=0, keepdims=True)
    dists = cdist(z, pattern)
    return 1 - (dists.ravel() / (dists.mean() + 2 * dists.std() + EPSILON))


def _calculate_synthetic_index_topsis(data: np.ndarray) -> np.ndarray:
    norm = np.sqrt((data**2).sum(axis=0)) + EPSILON
    v = data / norm
    v_plus = v.max(axis=0)
    v_minus = v.min(axis=0)
    d_plus = np.sqrt(((v - v_plus) ** 2).sum(axis=1))
    d_minus = np.sqrt(((v - v_minus) ** 2).sum(axis=1))
    return d_minus / (d_plus + d_minus + EPSILON)


def prep_to_evaluation(
    data: pd.DataFrame,
    heat_ind: str,
    area: str,
    h3_col: str,
    heat_dist: str,
    gini_indicator: bool,
    lorenz_gini: bool,
    method_gini: str,
) -> pd.DataFrame:
    """Calculate variables needed for multi-criteria evaluation per H3 hexagon."""
    # Validate inputs
    if data is None or data.empty:
        raise ValidationError("Input data for evaluation is empty")

    required_cols = [h3_col, area, heat_dist]
    if heat_ind:
        required_cols.append(heat_ind)
    missing = [c for c in required_cols if c not in data.columns]
    if missing:
        raise ValidationError(f"Missing required columns in prep_to_evaluation: {missing}")

    df = data.copy()

    df["heat_area"] = df.get(heat_ind, 0).astype(float) * df.get(area, 0).astype(float)
    grouped = df.groupby(h3_col, dropna=True)

    logger.info(f"Processing {len(df)} buildings grouped into {grouped.ngroups} H3 hexagons")
    if gini_indicator:
        agg = grouped.agg(
            powierzchnia=(area, "sum"),
            heat_area=("heat_area", "sum"),
            gini=(area, _compute_gini_placeholder),
            median_heat=(heat_dist, "median"),
        ).reset_index()
    else:
        agg = grouped.agg(
            powierzchnia=(area, "sum"),
            heat_area=("heat_area", "sum"),
            median_heat=(heat_dist, "median"),
        ).reset_index()

    # Remove zeros in denominator, compute connectivity flags
    agg["median_heat"] = agg["median_heat"].apply(
        lambda v: MIN_HEAT_DISTANCE if pd.isna(v) or v < MIN_HEAT_DISTANCE else v
    )
    agg["connectivity"] = (agg["heat_area"] / agg["powierzchnia"]).fillna(0) > CONNECTIVITY_THRESHOLD
    agg["alternative_connectivity"] = agg["powierzchnia"] / agg["median_heat"]

    connected = set(agg.loc[agg["connectivity"], h3_col].dropna().astype(str))

    agg["denominator"] = agg[h3_col].astype(str).apply(lambda idx: _compute_min_grid_distance(idx, connected))
    agg["heat_connectivity"] = agg["powierzchnia"] / (agg["denominator"].astype(float) + 1.0)

    val_map = dict(zip(agg[h3_col].astype(str), agg["heat_connectivity"].astype(float)))
    agg["neighbor"] = agg[h3_col].astype(str).apply(lambda idx: _compute_median_neighbor_value(idx, val_map))

    cols = [h3_col, "heat_connectivity", "neighbor", "alternative_connectivity"]
    if gini_indicator:
        cols = [h3_col, "gini", *cols]

    result = agg[cols].copy()
    logger.info(
        f"Evaluation preparation complete: {len(result)} H3 hexagons with "
        f"{len(cols) - 1} metrics (Gini: {gini_indicator})"
    )
    return result


def _compute_gini_placeholder(values: pd.Series) -> float:
    """Small adapter to compute Gini without introducing a circular import.

    The original implementation used a module-level function; keep it lightweight.
    """
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


def miernik_syntetyczny(
    data: pd.DataFrame,
    var_stymulanta: list[str],
    var_destymulanta: list[str] | None = None,
    classification: bool = False,
    method: str = "average",
) -> pd.DataFrame:
    """Calculate multi-criteria decision index and optional classification."""
    logger.debug(f"Computing synthetic index using method: {method}")

    if data is None or data.empty:
        raise ValidationError("Input data for synthetic index is empty")
    missing = [c for c in var_stymulanta if c not in data.columns]
    if missing:
        raise ValidationError(f"Missing stimulant columns: {missing}")
    if var_destymulanta:
        missing = [c for c in var_destymulanta if c not in data.columns]
        if missing:
            raise ValidationError(f"Missing destimulant columns: {missing}")

    valid_methods = ["average", "volatility", "distance", "topsis"]
    if method not in valid_methods:
        raise ValidationError(f"Invalid method '{method}'. Must be one of: {valid_methods}")

    result_df = data.copy()
    stym = data[var_stymulanta].to_numpy(dtype=float)
    if var_destymulanta:
        dest = 1.0 - data[var_destymulanta].to_numpy(dtype=float)
        df_temp = np.concatenate([stym, dest], axis=1)
    else:
        df_temp = stym

    if method == "average":
        index_var = _calculate_synthetic_index_average(df_temp)
    elif method == "volatility":
        index_var = _calculate_synthetic_index_volatility(df_temp)
    elif method == "distance":
        index_var = _calculate_synthetic_index_distance(df_temp)
    else:
        index_var = _calculate_synthetic_index_topsis(df_temp)

    result_df["index"] = index_var

    logger.info(
        f"Synthetic index computed for {len(result_df)} records. "
        f"Mean: {index_var.mean():.4f}, Std: {index_var.std():.4f}"
    )

    if classification:
        mean_index = float(index_var.mean())
        sd_index = float(index_var.std(ddof=0))
        from .constants import CLASSIFICATION_LABELS

        result_df["classification"] = pd.cut(
            result_df["index"],
            bins=[
                -float("inf"),
                mean_index - sd_index,
                mean_index,
                mean_index + sd_index,
                float("inf"),
            ],
            labels=CLASSIFICATION_LABELS,
            include_lowest=True,
        )

        class_counts = result_df["classification"].value_counts()
        logger.info(f"Classification distribution: {class_counts.to_dict()}")

    return result_df


__all__ = ["prep_to_evaluation", "miernik_syntetyczny"]
