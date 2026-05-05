import numpy as np
import pandas as pd

# ---------------------------
# VIM::kNN
# ---------------------------


def vim_knn_impute(
    dataframe: pd.DataFrame,
    variables: list[str],
    *,
    k: int = 10,
    distance_variables: list[str] | None = None,
    weight_mode: str = "one_minus_distance",  # "one_minus_distance" | "inverse_distance" | "uniform"
    tie_break: str = "deterministic",  # "random" | "deterministic"
    seed: int | None = None,
) -> pd.DataFrame:
    """
    Mixed k-NN in the style of VIM::kNN:
    - Distance: Gower distance over distance_variables (default = variables).
    - Numerics: min–max scaling; imputation = weighted mean.
    - Categoricals: weighted majority vote.
    It imputes only the columns listed in variables.

    Args:
        dataframe : input data.
        variables : columns to impute.
        k : number of nearest neighbors.
        distance_variables : columns used for distance; defaults to variables.
        weight_mode : neighbor weighting scheme ("one_minus_distance", "inverse_distance", "uniform").
        tie_break : tie-breaking mode for neighbors ("deterministic", "random").
        seed : seed used when tie_break="random".

    Returns:
        copy of dataframe[variables] with missing values imputed.
    """
    all_data = dataframe.copy()

    if distance_variables is None:
        distance_variables = list(variables)
    else:
        distance_variables = [column for column in distance_variables if column in all_data.columns]

    variables_missing = [v for v in variables if v not in all_data.columns]
    if variables_missing:
        raise KeyError(
            f"vim_knn_impute: missing variables in dataframe: {variables_missing}. "
            f"Present columns: {list(all_data.columns)}"
        )

    numeric_columns = [
        column
        for column in distance_variables
        if column in all_data.columns and pd.api.types.is_numeric_dtype(all_data[column])
    ]
    categorical_columns = [
        column
        for column in distance_variables
        if column in all_data.columns and not pd.api.types.is_numeric_dtype(all_data[column])
    ]

    epsilon = 1e-12
    numeric_min: dict[str, float] = {}
    numeric_range: dict[str, float] = {}
    for column in numeric_columns:
        numeric_series = pd.to_numeric(all_data[column], errors="coerce")
        minimum = numeric_series.min(skipna=True)
        maximum = numeric_series.max(skipna=True)
        if pd.isna(minimum) or pd.isna(maximum) or maximum == minimum:
            numeric_min[column] = float(minimum) if pd.notna(minimum) else 0.0
            numeric_range[column] = np.nan
        else:
            numeric_min[column] = float(minimum)
            numeric_range[column] = float(maximum - minimum)

    random_generator = np.random.default_rng(seed) if tie_break == "random" else None

    def gower_distance_to_all(row_index: int, donor_indices: np.ndarray) -> np.ndarray:
        donors_count = len(donor_indices)
        if donors_count == 0:
            return np.array([], dtype=float)
        distance_sum = np.zeros(donors_count, dtype=float)
        distance_count = np.zeros(donors_count, dtype=float)

        for column in numeric_columns:
            column_range = numeric_range[column]
            if not np.isfinite(column_range):
                continue
            value_i = pd.to_numeric(all_data.at[row_index, column], errors="coerce")
            values_j = pd.to_numeric(all_data.loc[donor_indices, column], errors="coerce").to_numpy()
            mask = np.isfinite(value_i) & np.isfinite(values_j)
            if mask.any():
                difference = np.zeros(donors_count, dtype=float)
                difference[mask] = np.abs(values_j[mask] - float(value_i)) / (column_range + epsilon)
                distance_sum += difference
                distance_count += mask.astype(float)

        for column in categorical_columns:
            value_i = all_data.at[row_index, column]
            values_j = all_data.loc[donor_indices, column].to_numpy(object)
            mask = pd.notna(value_i) & pd.notna(values_j)
            if mask.any():
                not_equal = np.zeros(donors_count, dtype=float)
                not_equal[mask] = (values_j[mask] != value_i).astype(float)
                distance_sum += not_equal
                distance_count += mask.astype(float)

        output = np.ones(donors_count, dtype=float)
        valid = distance_count > 0
        output[valid] = distance_sum[valid] / distance_count[valid]
        return output

    variables = [column for column in variables if column in all_data.columns]

    result = all_data[variables].copy()

    number_of_rows = len(all_data)
    base_order = np.arange(number_of_rows)
    if random_generator is not None:
        base_order = random_generator.permutation(number_of_rows)

    for variable in variables:
        column_series = all_data[variable]
        missing_indices = np.where(column_series.isna().to_numpy())[0]
        if missing_indices.size == 0:
            continue

        donor_indices = np.where(column_series.notna().to_numpy())[0]
        if donor_indices.size == 0:
            continue

        donor_tie_breaker = base_order[donor_indices]
        is_numeric_target = pd.api.types.is_numeric_dtype(column_series)

        for row_index in missing_indices:
            distances = gower_distance_to_all(row_index, donor_indices)
            if distances.size == 0:
                continue

            order = np.lexsort((donor_tie_breaker, distances))
            effective_k = min(k, order.size)
            selected_indices = order[:effective_k]
            nearest_neighbors = donor_indices[selected_indices]
            nearest_distances = distances[selected_indices]
            nearest_tie_values = donor_tie_breaker[selected_indices]

            if weight_mode == "one_minus_distance":
                weights = 1.0 - nearest_distances
            elif weight_mode == "inverse_distance":
                weights = 1.0 / (nearest_distances + epsilon)
            elif weight_mode == "uniform":
                weights = np.ones_like(nearest_distances)
            else:
                raise ValueError(f"Unknown weight_mode='{weight_mode}'")

            if not np.isfinite(weights).any() or float(weights.sum()) <= epsilon:
                weights = np.ones_like(nearest_distances)

            if is_numeric_target:
                neighbor_values = pd.to_numeric(all_data.loc[nearest_neighbors, variable], errors="coerce").to_numpy()
                mask = np.isfinite(neighbor_values) & np.isfinite(weights)
                if not mask.any():
                    continue
                result.at[all_data.index[row_index], variable] = np.average(
                    neighbor_values[mask], weights=weights[mask]
                )
            else:
                stable_order = np.argsort(nearest_tie_values, kind="mergesort")
                neighbor_values = all_data.loc[nearest_neighbors, variable].astype(object).to_numpy()[stable_order]
                neighbor_weights = weights[stable_order]

                weights_by_category: dict[object, float] = {}
                for category, category_weight in zip(neighbor_values, neighbor_weights):
                    if pd.isna(category):
                        continue
                    weights_by_category[category] = weights_by_category.get(category, 0.0) + float(category_weight)

                if not weights_by_category:
                    continue
                best_category = max(weights_by_category.items(), key=lambda item: item[1])[0]
                result.at[all_data.index[row_index], variable] = best_category

    return result
