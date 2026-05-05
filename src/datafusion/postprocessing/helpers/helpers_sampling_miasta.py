import logging

import numpy as np
import pandas as pd

from datafusion.configs.postprocessing_config import ColumnsConfig, PostprocessingConfig
from datafusion.postprocessing.helpers.r_sampling_algorithms import inclusion_probabilities
from datafusion.utils.validation import require_columns

logger = logging.getLogger(__name__)

# ---------------------------
# Preprocessing helpers
# ---------------------------


def normalize_size_map(sampling_frame: pd.DataFrame, strata_column: str, size_by_stratum: dict) -> dict:
    """
    Ensure size_by_stratum covers all strata seen in data.
    Missing -> 0.0 (warn), extra -> warn. Validates [0,1).
    """
    if sampling_frame.empty:
        logger.warning("normalize_size_map: sampling_frame is empty – returning empty size map.")
        return {}

    require_columns(sampling_frame, [strata_column], context="normalize_size_map(strata_column)")

    levels = sorted(sampling_frame[strata_column].dropna().astype(str).unique().tolist())

    try:
        normalized_map = {str(key): float(value) for key, value in (size_by_stratum or {}).items()}
    except (ValueError, TypeError) as e:
        raise ValueError(f"size_by_stratum contains non-numeric values: {e}") from e

    missing = [level for level in levels if level not in normalized_map]
    extra = [key for key in normalized_map.keys() if key not in levels]

    if missing:
        logger.warning("Missing fractions for strata %s → setting 0.0", missing)
        for level in missing:
            normalized_map[level] = 0.0
    if extra:
        logger.warning("Extra keys in size_by_stratum not present in data: %s", extra)

    invalid = [key for key, value in normalized_map.items() if not (0.0 <= value < 1.0)]

    if invalid:
        raise ValueError(f"Fractions must be in [0,1): {invalid}")

    return normalized_map


def apply_filters(dataframe: pd.DataFrame, config: PostprocessingConfig, columns: ColumnsConfig) -> pd.DataFrame:
    """Apply initial row filters."""
    if dataframe.empty:
        logger.warning("apply_filters: input dataframe is empty – nothing to filter.")
        return dataframe.copy()

    status_column = columns.status
    inventory_flag_column = columns.inwentaryzacja_flag

    mask = pd.Series(True, index=dataframe.index)

    filters_config = config.filters
    drop_status = set(filters_config.drop_if_status_in)
    if status_column in dataframe.columns and drop_status:
        mask &= ~dataframe[status_column].isin(drop_status)

    drop_inventory = set(filters_config.drop_if_inwentaryzacja_in)
    if inventory_flag_column in dataframe.columns and drop_inventory:
        mask &= ~dataframe[inventory_flag_column].isin(drop_inventory)

    for column_name in filters_config.require_non_null:
        if column_name in dataframe.columns:
            mask &= dataframe[column_name].notna() & (dataframe[column_name].astype(str).str.strip().str.len() > 0)

    filtered = dataframe.loc[mask].copy()
    if filtered.empty:
        logger.warning("apply_filters: all rows were filtered out – resulting dataframe is empty.")
    return filtered


def fill_power_columns(dataframe: pd.DataFrame, columns: ColumnsConfig) -> pd.DataFrame:
    """Fix pow_uzytkowa_m2 using pow_obrysu_m2 for NA/0."""
    if dataframe.empty:
        logger.warning("fill_power_columns: input dataframe is empty.")
        return dataframe.copy()

    usable_area_column = columns.pow_uzytkowa
    footprint_area_column = columns.pow_obrysu

    require_columns(
        dataframe,
        [usable_area_column, footprint_area_column],
        context="fill_power_columns",
    )

    output = dataframe.copy()
    output[usable_area_column] = np.where(
        output[usable_area_column].isna(),
        output[footprint_area_column],
        output[usable_area_column],
    )
    output[usable_area_column] = np.where(
        output[usable_area_column].eq(0),
        output[footprint_area_column],
        output[usable_area_column],
    )
    return output


def add_strata_label(dataframe: pd.DataFrame, columns: ColumnsConfig) -> pd.DataFrame:
    """Create composite 'strata' label."""
    if dataframe.empty:
        logger.warning("add_strata_label: input dataframe is empty.")
        return dataframe.copy()

    building_type_column = columns.rodzaj_budynku
    central_heating_column = columns.centralne
    h3_column = columns.h3
    hot_water_column = columns.cwu

    require_columns(
        dataframe,
        [building_type_column, central_heating_column, h3_column, hot_water_column],
        context="add_strata_label",
    )

    output = dataframe.copy()
    output["strata"] = (
        output[building_type_column].astype(str)
        + " "
        + output[central_heating_column].astype(str)
        + " "
        + output[h3_column].astype(str)
        + " "
        + output[hot_water_column].astype(str)
    )
    return output


def add_latent_area(dataframe: pd.DataFrame, columns: ColumnsConfig) -> pd.DataFrame:
    """latent_area = pow_uzytkowa_m2 * weight (or pow_uzytkowa_m2 if weight NA)."""
    if dataframe.empty:
        logger.warning("add_latent_area: input dataframe is empty.")
        return dataframe.copy()

    usable_area_column = columns.pow_uzytkowa
    weight_column = columns.weight

    require_columns(
        dataframe,
        [usable_area_column, weight_column],
        context="add_latent_area",
    )

    output = dataframe.copy()
    output["latent_area"] = np.where(
        output[weight_column].isna(),
        output[usable_area_column],
        output[usable_area_column] * output[weight_column],
    )
    return output


# ---------------------------
# PPS + balanced sampling
# ---------------------------


def inclusion_probabilities_certainty(size_measure, sample_size, eps: float = 1e-12):
    """
    Compute inclusion probabilities for probability-proportional-to-size (PPS) sampling
    with automatic detection of certainty units.

    Args:
    size_measure : size measures for each unit in the population
    sample_size : target sample size
    eps : numerical tolernace

    Returns:
    array of inclusion probabilities

    """
    size_measure = np.asarray(size_measure, float)
    sample_size = int(round(sample_size))
    if sample_size <= 0 or size_measure.sum() <= 0:
        return np.zeros_like(size_measure)
    inclusion_probs = np.zeros_like(size_measure, float)
    indices = np.arange(len(size_measure))
    working_weights = size_measure.copy()
    remaining_sample_size = sample_size
    remaining_indices = indices
    while remaining_sample_size > 0 and working_weights.sum() > 0 and len(remaining_indices) > 0:
        probabilities = remaining_sample_size * working_weights / working_weights.sum()
        certainty_mask = probabilities >= 1 - eps
        if certainty_mask.any():
            inclusion_probs[remaining_indices[certainty_mask]] = 1.0
            remaining_sample_size -= certainty_mask.sum()
            keep_mask = ~certainty_mask
            remaining_indices = remaining_indices[keep_mask]
            working_weights = working_weights[keep_mask]
        else:
            inclusion_probs[remaining_indices] = probabilities
            remaining_sample_size = 0
    return inclusion_probs


def pps_multiway(
    data: pd.DataFrame,
    strata_col: str,
    multiway_cols: list[str],
    size_variable: str,
    size_by_stratum: dict[str, float] | None = None,
    size_vector: list[float] | None = None,
) -> pd.DataFrame:
    """
    Compute PPS inclusion probabilities within strata and multiway sub-strata.
    Each stratum is allocated a sampling fraction, and each multiway subgroup
    receives a ceiling-based sample size, similar to R’s PPS multiway allocation.

    Args:
        data : Input dataset.
        strata_col : column defining strata.
        multiway_cols : columns defining multiway sub-strata.
        size_variable : size measure variable used for PPS.
        size_by_stratum : optional mapping of stratum → sampling fraction.
        size_vector : optional fractions aligned with sorted strata.

    Returns:
        original rows with an added 'prob' column of PPS inclusion probabilities.
    """
    if data.empty:
        logger.warning("pps_multiway: input data is empty – returning empty dataframe.")
        return data.copy()

    require_columns(
        data,
        [strata_col, size_variable] + list(multiway_cols),
        context="pps_multiway",
    )

    parts: list[pd.DataFrame] = []

    strata_values = data[strata_col].astype(str).fillna("").unique().tolist()
    if size_by_stratum:

        def get_size(s):
            return float(size_by_stratum.get(str(s), 0.0))
    else:
        strata_values_sorted = sorted(strata_values)
        if size_vector is None or len(size_vector) != len(strata_values_sorted):
            raise ValueError("Provide size_by_stratum or size_vector matching alphabetical strata.")
        size_map = {level: float(size_vector[i]) for i, level in enumerate(strata_values_sorted)}

        def get_size(s):
            return size_map[str(s)]

    for level, group in data.groupby(strata_col, dropna=False):
        fraction = get_size(level)
        temp = group.copy()
        temp["multiway"] = temp[multiway_cols].astype(str).agg("_".join, axis=1)

        if fraction <= 0:
            temp["prob"] = 0.0
            parts.append(temp)
            continue

        subgroups = [(multiway_value, sub.copy()) for multiway_value, sub in temp.groupby("multiway", dropna=False)]
        subgroup_sizes = np.array([len(subgroup[1]) for subgroup in subgroups], dtype=float)

        base_sample_sizes = np.ceil(subgroup_sizes * fraction).astype(int)

        for (_, sub), sample_size in zip(subgroups, base_sample_sizes.tolist()):
            inclusion_probs = inclusion_probabilities(sub[size_variable].to_numpy(), int(sample_size))
            sub["prob"] = inclusion_probs
            parts.append(sub)

    if not parts:
        logger.warning("pps_multiway: no strata processed – returning empty dataframe with original columns.")
        return data.copy()

    return pd.concat(parts, ignore_index=True)


def _build_balancing_matrices(
    temp_df: pd.DataFrame,
    pik_col: str,
    marginal_strata: list[str],
    aux_vars: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build feature_matrix, pik, target for balancing."""
    needed_cols = [pik_col] + list(marginal_strata) + list(aux_vars)
    needed_cols = [c for c in needed_cols if c]  # na wszelki wypadek
    require_columns(temp_df, needed_cols, context="_build_balancing_matrices")

    onehots = []
    for col in marginal_strata:
        onehot = pd.get_dummies(temp_df[col].astype(str), prefix=col, drop_first=False)
        onehots.append(onehot)
    categorical_features = pd.concat(onehots, axis=1) if onehots else pd.DataFrame(index=temp_df.index)
    auxiliary_features = temp_df[aux_vars].copy() if aux_vars else pd.DataFrame(index=temp_df.index)
    feature_matrix = pd.concat([categorical_features, auxiliary_features], axis=1).to_numpy(dtype=float)
    pik = temp_df[pik_col].to_numpy(dtype=float)
    target = feature_matrix.T @ pik
    return feature_matrix, pik, target


def _greedy_balance_swap(
    feature_matrix: np.ndarray,
    pik: np.ndarray,
    target: np.ndarray,
    init_select: np.ndarray,
    iters: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Local 1↔1 swap to reduce ||feature_matrix^T s - target||.

    Args:
    temp_df : input data.
    pik_col : column with inclusion probabilities.
    marginal_strata : categorical variables expanded into one-hot blocks.
    aux_vars : numeric auxiliary variables.

    Returns:
        matrix feature_matrix, vector pik, and balancing target totals.

    """
    selection = init_select.copy()
    feature_matrix_transposed = feature_matrix.T
    current = feature_matrix_transposed @ selection
    error = np.linalg.norm(current - target)

    chosen_indices = np.where(selection == 1)[0].tolist()
    not_chosen_indices = np.where(selection == 0)[0].tolist()
    if not chosen_indices or not not_chosen_indices:
        return selection

    for _ in range(max(0, int(iters))):
        i = rng.choice(chosen_indices)
        j = rng.choice(not_chosen_indices)
        delta = feature_matrix_transposed[:, j] - feature_matrix_transposed[:, i]
        new_current = current + delta
        new_error = np.linalg.norm(new_current - target)
        if new_error + 1e-12 < error:
            selection[i] = 0
            selection[j] = 1
            current = new_current
            error = new_error
            chosen_indices.remove(i)
            not_chosen_indices.remove(j)
            chosen_indices.append(j)
            not_chosen_indices.append(i)
    return selection


def strata_multiway_balanced_heur(
    data: pd.DataFrame,
    pik_col: str,
    strata_col: str,
    marginal_strata: list[str],
    aux_vars: list[str],
    seed: int,
    iters: int,
) -> pd.DataFrame:
    """
    Heuristic stratified balanced sampling with multiway strata and auxiliary
    variables, using a greedy swap adjustment of an initial PPS draw.

    Args:
        data : Input data.
        pik_col : Column with inclusion probabilities.
        strata_col : Column defining primary strata.
        marginal_strata : Categorical variables for marginal balancing.
        aux_vars : Numeric auxiliary variables for balancing.
        seed : Random seed for the RNG.
        iters : Number of greedy swap iterations.

    Returns:
        DataFrame, Original data with an added 'sample_ind' indicator (0/1).
    """
    if data.empty:
        logger.warning("strata_multiway_balanced_heur: input data is empty.")
        return data.copy()

    require_columns(
        data,
        [pik_col, strata_col] + list(marginal_strata) + list(aux_vars),
        context="strata_multiway_balanced_heur",
    )

    rng = np.random.default_rng(seed)
    out_parts: list[pd.DataFrame] = []

    for _, temp in data.groupby(strata_col, dropna=False):
        temp = temp.copy()
        feature_matrix, pik, target = _build_balancing_matrices(
            temp_df=temp,
            pik_col=pik_col,
            marginal_strata=marginal_strata,
            aux_vars=aux_vars,
        )

        n_target = int(np.round(float(pik.sum())))
        n_target = max(0, min(n_target, len(temp)))

        if n_target > 0 and pik.sum() > 0:
            indices = np.arange(len(temp))
            probabilities = pik / pik.sum()
            chosen = rng.choice(indices, size=n_target, replace=False, p=probabilities)
            initial_selection = np.zeros(len(temp), dtype=int)
            initial_selection[chosen] = 1
            selection = _greedy_balance_swap(feature_matrix, pik, target, initial_selection, iters=iters, rng=rng)
        else:
            selection = np.zeros(len(temp), dtype=int)

        difference = int(n_target - selection.sum())
        if difference != 0:
            if difference > 0:
                pool = np.where(selection == 0)[0]
                add = rng.choice(pool, size=min(difference, len(pool)), replace=False)
                selection[add] = 1
            else:
                pool = np.where(selection == 1)[0]
                remove = rng.choice(pool, size=min(-difference, len(pool)), replace=False)
                selection[remove] = 0

        temp["sample_ind"] = selection
        out_parts.append(temp)

    return pd.concat(out_parts, ignore_index=True)


def _standardize_cols(feature_matrix: np.ndarray, eps: float = 1e-12) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Standarize column values."""
    mean_vector = feature_matrix.mean(axis=0, keepdims=True)
    centered = feature_matrix - mean_vector
    norm_vector = np.linalg.norm(centered, axis=0, keepdims=True)
    norm_vector = np.where(norm_vector < eps, 1.0, norm_vector)
    return centered / norm_vector, mean_vector, norm_vector


def _nearest_neighbor_pairs(feature_matrix_standardized: np.ndarray, rng: np.random.Generator) -> list[tuple[int, int]]:
    """
    Form nearest-neighbor index pairs based on Euclidean distance, using a
    randomized order to initiate pairing.

    Args:
        feature_matrix_standardized : matrix of feature vectors.
        rng : random generator for shuffling.

    Returns:
        pairs of indices
    """
    n = feature_matrix_standardized.shape[0]
    remaining = list(range(n))
    rng.shuffle(remaining)
    pairs: list[tuple[int, int]] = []
    while len(remaining) > 1:
        i = remaining.pop()
        xi = feature_matrix_standardized[i]
        rest = np.array(remaining)
        d2 = ((feature_matrix_standardized[rest] - xi) ** 2).sum(axis=1)
        j_idx = int(rest[np.argmin(d2)])
        remaining.remove(j_idx)
        pairs.append((i, j_idx))
    if remaining:
        pairs.append((remaining[0], remaining[0]))
    return pairs


def _local_pivotal(feature_matrix: np.ndarray, pik: np.ndarray, seed: int, max_passes: int = 1) -> np.ndarray:
    """
    Apply the local pivotal method to convert inclusion probabilities into a
    balanced zero–one sample, using nearest-neighbor pairing and randomized
    resolution of fractional probabilities.

    Args:
        feature_matrix : feature matrix used to guide local pairing.
        pik : initial inclusion probabilities.
        seed : seed for randomization.
        max_passes : number of full pairing passes over the data.

    Returns:
        final 0/1 selection vector produced by the pivotal algorithm.
    """
    rng = np.random.default_rng(seed)
    feature_matrix_standardized, _, _ = _standardize_cols(feature_matrix)
    p = pik.astype(float).copy()
    for _ in range(max_passes):
        for i, j in _nearest_neighbor_pairs(feature_matrix_standardized, rng):
            if i == j:
                p[i] = 1.0 if rng.random() < p[i] else 0.0
                continue
            s = p[i] + p[j]
            u = rng.random()
            if u < p[i] / s:
                p[i] = 1.0
                p[j] = s - 1.0
            else:
                p[i] = s - 1.0
                p[j] = 1.0
            p[i] = 1.0 if p[i] >= 1.0 else (0.0 if p[i] <= 0.0 else p[i])
            p[j] = 1.0 if p[j] >= 1.0 else (0.0 if p[j] <= 0.0 else p[j])
    fractional_mask = (p > 0) & (p < 1)
    p[fractional_mask] = (np.random.default_rng(seed + 1).random(fractional_mask.sum()) < p[fractional_mask]).astype(
        float
    )
    return p


def strata_multiway_cubeish(
    data: pd.DataFrame,
    pik_col: str,
    strata_col: str,
    marginal_strata: list[str],
    aux_vars: list[str],
    seed: int,
    iters: int,
) -> pd.DataFrame:
    """
    Stratified balanced sampling using a faster heuristic.
    Uses PPS sampling followed by greedy balance refinement.

    Args:
        data : input data.
        pik_col : column with inclusion probabilities.
        strata_col : column defining primary strata.
        marginal_strata : categorical variables for marginal balancing.
        aux_vars : numeric auxiliary variables for balancing.
        seed : seed for randomization.
        iters : number of greedy balance-swap iterations.

    Returns:
        original data with an added 'sample_ind' indicator (0/1).
    """
    if data.empty:
        logger.warning("strata_multiway_cubeish: input data is empty.")
        return data.copy()

    require_columns(
        data,
        [pik_col, strata_col] + list(marginal_strata) + list(aux_vars),
        context="strata_multiway_cubeish",
    )

    rng = np.random.default_rng(seed)
    out: list[pd.DataFrame] = []

    for _stratum_value, temp in data.groupby(strata_col, dropna=False):
        temp = temp.copy()

        onehots = []
        for col in marginal_strata:
            onehot = pd.get_dummies(temp[col].astype(str), prefix=col, drop_first=False)
            onehots.append(onehot)
        categorical_features = pd.concat(onehots, axis=1) if onehots else pd.DataFrame(index=temp.index)
        auxiliary_features = temp[aux_vars].copy() if aux_vars else pd.DataFrame(index=temp.index)

        feature_matrix = pd.concat([categorical_features, auxiliary_features], axis=1).to_numpy(float)

        pik = temp[pik_col].to_numpy(float)
        if categorical_features.shape[1] > 0:
            k = categorical_features.shape[1]
            feature_matrix[:, :k] = feature_matrix[:, :k] * pik[:, None]

        target = feature_matrix.T @ pik

        n_target = int(np.round(pik.sum()))
        if n_target > 0 and pik.sum() > 0:
            indices = np.arange(len(temp))
            probabilities = pik / pik.sum()
            chosen = rng.choice(indices, size=n_target, replace=False, p=probabilities)
            selection = np.zeros(len(temp), dtype=int)
            selection[chosen] = 1
            selection = _greedy_balance_swap(feature_matrix, pik, target, selection, iters=iters, rng=rng)
        else:
            selection = np.zeros(len(temp), dtype=int)

        n_target = int(np.round(pik.sum()))
        difference = n_target - int(selection.sum())
        if difference != 0:
            if difference > 0:
                pool = np.where(selection == 0)[0]
                if len(pool) > 0:
                    add = rng.choice(pool, size=min(difference, len(pool)), replace=False)
                    selection[add] = 1
            else:
                pool = np.where(selection == 1)[0]
                if len(pool) > 0:
                    remove = rng.choice(pool, size=min(-difference, len(pool)), replace=False)
                    selection[remove] = 0

        temp["sample_ind"] = selection
        out.append(temp)

    return pd.concat(out, ignore_index=True)
