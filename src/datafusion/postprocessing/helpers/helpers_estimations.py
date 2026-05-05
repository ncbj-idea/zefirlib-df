import logging
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from datafusion.constants import TABLE_OPERAT_LOSOWANIA
from datafusion.utils.crud import load_dataframe_from_db
from datafusion.utils.validation import require_columns

logger = logging.getLogger(__name__)

# ---------------------------
# Inputs
# ---------------------------


def read_estimations_inputs(
    engine: Engine,
) -> dict[str, pd.DataFrame]:
    """Reads inputs for estimations parts."""

    operat_dataframe = load_dataframe_from_db(engine, TABLE_OPERAT_LOSOWANIA)
    estimation_dataframe = load_dataframe_from_db(engine, "data_to_estimation")

    if estimation_dataframe.empty:
        logging.info("Optional estimation file not found: %s — creating empty DataFrame.")
        estimation_dataframe = pd.DataFrame()

    if not operat_dataframe.empty:
        _normalize_bool_cols(operat_dataframe, ["heat_connected", "gas_connected", "h3_connectivity"])

    if not estimation_dataframe.empty:
        _normalize_bool_cols(estimation_dataframe, ["heat_connected", "gas_connected", "h3_connectivity"])

    data = {
        "operat": operat_dataframe,
        "estimation": estimation_dataframe,
    }
    return data


# ---------------------------
# Helpers
# ---------------------------


def _normalize_bool_cols(df: pd.DataFrame, cols: Iterable[str]) -> None:
    mapping = {
        True: True,
        False: False,
        "PRAWDA": True,
        "FAŁSZ": False,
        "TAK": True,
        "NIE": False,
        "TRUE": True,
        "FALSE": False,
        "1": True,
        "0": False,
    }
    for col in cols:
        if col not in df.columns:
            continue
        s = df[col]
        mask_str = s.map(lambda x: isinstance(x, str))
        s2 = s.copy()
        # Only apply string operations if there are actual string values
        if mask_str.any():
            try:
                s2.loc[mask_str] = s2.loc[mask_str].str.strip().str.upper()
            except AttributeError:
                # Fallback: convert to string first, then process
                s2.loc[mask_str] = s2.loc[mask_str].astype(str).str.strip().str.upper()
        df[col] = s2.map(lambda x: mapping.get(x, pd.NA)).astype("boolean")


def _ensure_directory(path: Path) -> None:
    """Ensures that parent directory of the given path exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


try:
    import h3
    import pandas as pd

    def h3_get_parent(h3_index: str, resolution: int) -> str:
        if h3_index is None or (isinstance(h3_index, float) and np.isnan(h3_index)) or pd.isna(h3_index):
            return h3_index

        fn = getattr(h3, "h3_to_parent", None) or getattr(h3, "cell_to_parent", None)
        if fn is None:
            raise AttributeError("h3: missing both h3_to_parent and cell_to_parent")

        return fn(str(h3_index), int(resolution))

except Exception:

    def h3_get_parent(h3_index: str, resolution: int) -> str:
        return h3_index


# ---------------------------
# Survey-like helpers
# ---------------------------


def survey_weighted_sum_table(
    dataframe: pd.DataFrame,
    value_column: str,
    group_by: Iterable[str],
    weight_column: str,
) -> pd.DataFrame:
    """
    Compute weighted sums of a value column across grouped categories, with
    validation of required columns and handling of empty input.

    Args:
        dataframe : input data.
        value_column : column whose values are to be weighted and summed.
        group_by : grouping variables.
        weight_column : column containing weights.

    Returns:
        grouped weighted sums with column 'Freq'.
    """
    group_by = list(group_by)
    if dataframe.empty:
        logging.warning("survey_weighted_sum_table: empty dataframe – returning empty result.")
        return pd.DataFrame(columns=group_by + ["Freq"])

    require_columns(
        dataframe,
        list(group_by) + [value_column, weight_column],
        context="survey_weighted_sum_table",
    )

    grouped = dataframe.groupby(list(group_by), dropna=False, observed=True)
    result = grouped.apply(lambda d: np.sum(d[value_column] * d[weight_column])).rename("Freq").reset_index()
    return result


def survey_ratio(
    dataframe: pd.DataFrame,
    numerator_mask: pd.Series,
    denominator_mask: pd.Series,
    numerator_value_column: str,
    denominator_value_column: str,
    weight_column: str,
) -> float:
    """
    Compute a weighted ratio, where numerator and denominator are defined by
    boolean masks and corresponding value columns.

    Args:
        dataframe : input data.
        numerator_mask : rows included in the numerator.
        denominator_mask : rows included in the denominator.
        numerator_value_column : value column for the numerator.
        denominator_value_column : value column for the denominator.
        weight_column : column containing weights.

    Returns:
        weighted ratio (0.0 if denominator is zero).
    """
    numerator = np.sum(
        dataframe.loc[numerator_mask, numerator_value_column] * dataframe.loc[numerator_mask, weight_column]
    )
    denominator = np.sum(
        dataframe.loc[denominator_mask, denominator_value_column] * dataframe.loc[denominator_mask, weight_column]
    )
    return float(numerator / denominator) if denominator != 0 else 0.0


def survey_ratio_point(
    dataframe: pd.DataFrame,
    numerator_mask: pd.Series,
    denominator_mask: pd.Series,
    numerator_value_column: str,
    denominator_value_column: str,
    weight_column: str,
) -> float:
    """
    Pure point ratio estimator on weights.

    Args:
        dataframe : input data.
        numerator_mask : rows included in the numerator.
        denominator_mask : rows included in the denominator.
        numerator_value_column : value column for the numerator.
        denominator_value_column : value column for the denominator.
        weight_column : column containing weights.

    Returns:
        weighted ratio (0.0 if denominator is zero).
    """

    require_columns(
        dataframe,
        [numerator_value_column, denominator_value_column, weight_column],
        context="survey_ratio_point",
    )

    weights = dataframe[weight_column].astype(float)
    numerator_values = dataframe[numerator_value_column].astype(float)
    denominator_values = dataframe[denominator_value_column].astype(float)
    numerator_index = numerator_mask.fillna(False).to_numpy()
    denominator_index = denominator_mask.fillna(False).to_numpy()
    numerator = float(np.sum(weights.to_numpy()[numerator_index] * numerator_values.to_numpy()[numerator_index]))
    denominator = float(
        np.sum(weights.to_numpy()[denominator_index] * denominator_values.to_numpy()[denominator_index])
    )
    return float(numerator / denominator) if denominator != 0 else 0.0


def survey_ratio_jackknife(
    dataframe: pd.DataFrame,
    numerator_mask: pd.Series,
    denominator_mask: pd.Series,
    numerator_value_column: str,
    denominator_value_column: str,
    weight_column: str,
    cluster_column: str | None = None,
    recalibrate_function: Callable[[pd.DataFrame], pd.Series] | None = None,
) -> tuple[float, float]:
    """
    Compute a jackknife (JK1) standard error for a weighted ratio estimator.

    Args:
        dataframe : input data.
        numerator_mask : Rows included in the numerator.
        denominator_mask : Rows included in the denominator.
        numerator_value_column : Value column for the numerator.
        denominator_value_column : Value column for the denominator.
        weight_column : column containing base weights.
        cluster_column : PSU identifier for delete-1 clusters; if None, delete-1 units.
        recalibrate_function : optional function → replica weights.

    Returns:
        point estimate of the ratio and its jackknife standard error.
    """
    require_columns(
        dataframe,
        [numerator_value_column, denominator_value_column, weight_column],
        context="survey_ratio_jackknife",
    )

    theta_full = survey_ratio_point(
        dataframe,
        numerator_mask,
        denominator_mask,
        numerator_value_column,
        denominator_value_column,
        weight_column,
    )

    if cluster_column is None or cluster_column not in dataframe.columns:
        groups = [(i, np.array([i])) for i in dataframe.index]
    else:
        groups = [
            (
                cluster_value,
                dataframe.index[dataframe[cluster_column] == cluster_value].to_numpy(),
            )
            for cluster_value in pd.Index(dataframe[cluster_column]).dropna().unique()
        ]

    thetas: list[float] = []
    for _, index_to_drop in groups:
        keep_mask = ~dataframe.index.isin(index_to_drop)

        if recalibrate_function is not None:
            replica_weights = recalibrate_function(dataframe.loc[keep_mask, :])
            weights_to_use = replica_weights
        else:
            weights_to_use = dataframe.loc[keep_mask, weight_column].astype(float)

        numerator_keep = (numerator_mask & keep_mask).fillna(False)
        denominator_keep = (denominator_mask & keep_mask).fillna(False)

        numerator_replica = float(
            np.sum(
                dataframe.loc[numerator_keep, numerator_value_column].astype(float) * weights_to_use.loc[numerator_keep]
            )
        )
        denominator_replica = float(
            np.sum(
                dataframe.loc[denominator_keep, denominator_value_column].astype(float)
                * weights_to_use.loc[denominator_keep]
            )
        )
        thetas.append(float(numerator_replica / denominator_replica) if denominator_replica != 0 else 0.0)

    m = len(thetas)
    if m <= 1:
        return theta_full, 0.0
    theta_mean = float(np.mean(thetas))
    variance_estimate = (m - 1) / m * float(np.sum((np.array(thetas) - theta_mean) ** 2))
    standard_error = float(np.sqrt(variance_estimate))
    return theta_full, standard_error


def raking_calibration(
    dataframe: pd.DataFrame,
    base_weight_column: str,
    feature_columns: Iterable[str],
    targets: dict[str, float],
    max_iterations: int = 10_000,
    tolerance: float = 1e-8,
    bounds: tuple[float, float] | None = None,
) -> pd.Series:
    """
    Calibrate survey weights by raking (iterative proportional fitting) to match
    given feature totals.

    Args:
        dataframe : input data.
        base_weight_column : column with initial weights.
        feature_columns : columns used as calibration margins.
        targets : mapping feature_column → target total.
        max_iterations : maximum number of raking iterations.
        tolerance : convergence threshold on weight changes.
        bounds : optional lower/upper bounds for weights.

    Returns:
        calibrated weights aligned with dataframe index.
    """
    feature_columns = list(feature_columns)

    require_columns(
        dataframe,
        [base_weight_column] + feature_columns,
        context="raking_calibration",
    )

    weights = dataframe[base_weight_column].astype(float).to_numpy(copy=True)
    if feature_columns:
        feature_matrix = dataframe[feature_columns].astype(float).to_numpy(copy=False)
        target_vector = np.array([targets.get(column, 0.0) for column in feature_columns], dtype=float)

        feature_matrix = np.nan_to_num(feature_matrix, nan=0.0, posinf=0.0, neginf=0.0)

        for _ in range(int(max_iterations)):
            previous_weights = weights.copy()
            for j in range(feature_matrix.shape[1]):
                column_values = feature_matrix[:, j]
                current_sum = float(np.sum(weights * column_values))
                target_value = float(target_vector[j])
                if current_sum <= 0 or target_value <= 0:
                    continue
                ratio = target_value / current_sum
                mask = column_values > 0
                weights[mask] *= ratio

                if bounds is not None:
                    lower_bound, upper_bound = bounds
                    if np.isfinite(lower_bound):
                        weights[mask] = np.maximum(weights[mask], lower_bound)
                    if np.isfinite(upper_bound):
                        weights[mask] = np.minimum(weights[mask], upper_bound)

            if np.max(np.abs(weights - previous_weights)) < tolerance:
                break

    return pd.Series(weights, index=dataframe.index, name="calibrated_weight")


# ---------------------------
# PPS
# ---------------------------


def pps_systematic(sample_sizes: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """
    Systematic Probability Proportional Size.
    """
    measures = np.maximum(sample_sizes.astype(float), 0.0)
    total = measures.sum()
    if total <= 0 or n <= 0:
        return np.zeros(len(measures), dtype=bool)
    n = min(n, len(measures))

    cumulative = np.cumsum(measures)
    step = total / n
    start = rng.uniform(0, step)
    ticks = start + step * np.arange(n)
    selected = np.zeros(len(measures), dtype=bool)

    index = 0
    for tick in ticks:
        while index < len(cumulative) and cumulative[index] < tick:
            index += 1
        if index < len(cumulative):
            selected[index] = True
    return selected


def translate_heat_source_column(col_name: str) -> str:
    """
    Translate English heat source names to Polish column names.
    Also handles 'cwu_' prefix.
    """
    prefix = ""
    name = col_name
    if col_name.startswith("cwu_"):
        prefix = "cwu_"
        name = col_name[4:]

    # Remove trailing underscores if any, and convert spaces to underscores for lookup
    lookup_name = name.replace("_", " ").strip()

    mapping = {
        "District heating": "Miejska_sieć_ciepłownicza",
        "Gas boiler": "Kocioł_gazowy",
        "Electric heating": "Ogrzewanie_elektryczne",
        "Heat pump": "Pompa_ciepła",
        "Old solid fuel boiler (Class 4 or below)": "boiler_old",
        "New solid fuel boiler (Class 5/Ekoprojekt)": "boiler_new",
        "Fireplace": "Kominek",
    }

    translated = mapping.get(lookup_name, lookup_name)

    # Re-normalize to snake_case for the final column name
    final_name = translated.replace(" ", "_")
    return f"{prefix}{final_name}"
