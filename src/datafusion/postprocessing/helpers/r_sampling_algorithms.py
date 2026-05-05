from __future__ import annotations

import logging

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

EPS = 1e-11


def inclusion_probabilities(size_measures: NDArray[np.floating], sample_size: int) -> NDArray[np.floating]:
    """
    Compute first-order inclusion probabilities for PPS sampling.

    This is a Python port of R's sampling::inclusion_probabilities function.
    Uses Chao (1982) algorithm for probability proportional to size sampling.

    Args:
        size_measures: Vector of positive numbers (size measures).
        sample_size: Sample size.

    Returns:
        Vector of inclusion probabilities where sum equals sample_size.
    """
    size_measures = np.asarray(size_measures, dtype=float)
    if size_measures.size == 0:
        return np.array([])

    n_zero = np.sum(size_measures == 0)
    if n_zero > 0:
        logger.warning("There are %d zero values in the initial vector a", n_zero)

    n_negative = np.sum(size_measures < 0)
    if n_negative > 0:
        logger.warning("There are %d negative value(s) shifted to zero", n_negative)
        size_measures = np.where(size_measures < 0, 0.0, size_measures)

    if np.all(size_measures == 0):
        return np.zeros_like(size_measures)

    pik_initial = sample_size * size_measures / np.sum(size_measures)

    if np.all(pik_initial == 0):
        return pik_initial

    positive_mask = pik_initial > 0
    pik = pik_initial[positive_mask].copy()

    certainty_mask = pik >= 1
    n_certainty = np.sum(certainty_mask)

    if n_certainty > 0:
        while True:
            non_certainty_mask = ~certainty_mask
            if np.sum(non_certainty_mask) == 0:
                break

            normalized = pik[non_certainty_mask]
            normalized = normalized / np.sum(normalized)
            pik[non_certainty_mask] = (sample_size - n_certainty) * normalized
            pik[certainty_mask] = 1.0

            certainty_mask = pik >= (1 - EPS)
            new_n_certainty = np.sum(certainty_mask)

            if new_n_certainty == n_certainty:
                break
            n_certainty = new_n_certainty

        pik_initial[positive_mask] = pik

    return pik_initial


def _reduce_matrix(matrix: NDArray[np.floating]) -> NDArray[np.floating]:
    """Reduce matrix using SVD, keeping components with singular values > EPS."""
    n_rows, n_cols = matrix.shape
    if n_cols == 0:
        return matrix

    left_singular_vectors, singular_values, right_singular_vectors = np.linalg.svd(matrix, full_matrices=False)

    if n_rows >= n_cols:
        keep_mask = singular_values > EPS
        return matrix[:, keep_mask]
    else:
        keep_mask = singular_values > EPS
        return right_singular_vectors[keep_mask, :].T


def _jump(
    design_matrix: NDArray[np.floating],
    pik: NDArray[np.floating],
) -> NDArray[np.floating]:
    """
    Single iteration of the jump function in the cube algorithm.
    This is an internal function used in fast_flight_cube.
    """
    n_units = len(pik)
    n_vars = round(design_matrix.shape[1] if design_matrix.ndim > 1 else len(design_matrix) / n_units)

    augmented_matrix = np.column_stack([design_matrix, np.zeros(n_units)])
    left_singular_vectors = np.linalg.svd(augmented_matrix, full_matrices=False)[0]
    kernel_vector = left_singular_vectors[:, n_vars]

    kernel_abs = np.abs(kernel_vector)
    active_mask = kernel_abs > EPS

    if not np.any(active_mask):
        return pik

    upper_bounds = (1 - pik[active_mask]) / kernel_vector[active_mask]
    lower_bounds = -pik[active_mask] / kernel_vector[active_mask]

    lambda_upper = np.min(upper_bounds[upper_bounds > 0]) if np.any(upper_bounds > 0) else np.inf
    lambda_lower = np.min(lower_bounds[lower_bounds > 0]) if np.any(lower_bounds > 0) else np.inf

    pik_upper = pik + lambda_upper * kernel_vector
    pik_lower = pik - lambda_lower * kernel_vector

    selection_prob = lambda_lower / (lambda_upper + lambda_lower) if (lambda_upper + lambda_lower) > 0 else 0.5

    if np.random.random() < selection_prob:
        pik_new = pik_upper
    else:
        pik_new = pik_lower

    pik_new = np.clip(pik_new, 0.0, 1.0)
    return pik_new


def _algo_fast_flight_cube(
    design_matrix: NDArray[np.floating],
    pik: NDArray[np.floating],
) -> NDArray[np.floating]:
    """
    Core algorithm for the flight phase of the cube method.
    Ported from R's sampling package.
    """
    n_units = len(pik)
    n_vars = round(design_matrix.shape[1])

    if n_units <= n_vars + 1:
        return pik.copy()

    scaled_matrix = design_matrix / pik[:, np.newaxis]
    active_sub_matrix = scaled_matrix[: (n_vars + 1), :].copy()
    active_probs = pik[: (n_vars + 1)].copy()
    active_indices = np.arange(1, n_vars + 2)

    replacement_idx = n_vars + 2

    while replacement_idx <= n_units:
        active_probs = _jump(active_sub_matrix, active_probs)

        is_fixed = (active_probs > (1 - EPS)) | (active_probs < EPS)
        i = 0
        while i <= n_vars and replacement_idx <= n_units:
            i += 1
            if is_fixed[i - 1]:
                pik[active_indices[i - 1]] = active_probs[i - 1]
                active_probs[i - 1] = pik[replacement_idx - 1]
                active_sub_matrix[i - 1, :] = scaled_matrix[replacement_idx - 1, :]
                active_indices[i - 1] = replacement_idx
                replacement_idx += 1

    if np.sum((pik > EPS) & (pik < (1 - EPS))) == (n_vars + 1):
        active_probs = _jump(active_sub_matrix, active_probs)

    pik[active_indices - 1] = active_probs
    return pik


def fast_flight_cube(
    auxiliary_matrix: NDArray[np.floating],
    pik: NDArray[np.floating],
    order: int = 1,
    comment: bool = False,
) -> NDArray[np.floating]:
    """
    Fast flight phase of the cube method.
    Ported from R's sampling::fastflightcube function.

    Args:
        auxiliary_matrix: Matrix of balancing auxiliary variables (n_units x n_vars).
        pik: Vector of inclusion probabilities.
        order: 1=random, 2=no change, 3=decreasing order of pik.
        comment: If True, print progress information.

    Returns:
        Vector of updated inclusion probabilities after flight phase.
    """
    n_units = len(pik)
    n_vars = round(auxiliary_matrix.shape[1] if auxiliary_matrix.ndim > 1 else auxiliary_matrix.shape[0] / n_units)

    if order == 1:
        perm_order = np.random.permutation(n_units)
    elif order == 2:
        perm_order = np.arange(n_units)
    else:
        perm_order = np.argsort(-pik)

    valid_mask = (pik[perm_order] > EPS) & (pik[perm_order] < (1 - EPS))
    non_integer_indices = perm_order[valid_mask]

    if comment:
        logger.info("BEGINNING OF THE FLIGHT PHASE")
        logger.info("Matrix has %d variables and %d units", n_vars, n_units)
        logger.info("Inclusion probability sum: %.4f", np.sum(pik))
        logger.info("Non-integer elements: %d", len(non_integer_indices))

    pik_star = pik.copy()

    if len(non_integer_indices) > n_vars:
        if comment:
            logger.info("Step 1")

        pik_subset = pik[non_integer_indices]
        n_subset = len(pik_subset)
        aux_subset = auxiliary_matrix[non_integer_indices, :]

        pik_star_subset = _algo_fast_flight_cube(aux_subset, pik_subset)
        pik_star[non_integer_indices] = pik_star_subset

    non_integer_indices = perm_order[(pik_star[perm_order] > EPS) & (pik_star[perm_order] < (1 - EPS))]
    pik_subset = pik_star[non_integer_indices]
    n_subset = len(pik_subset)

    if n_subset > 0:
        aux_subset = auxiliary_matrix[non_integer_indices, :]
        aux_subset = _reduce_matrix(aux_subset)
        n_reduced_vars = aux_subset.shape[1]
    else:
        n_reduced_vars = 0

    step = 2
    while n_subset > n_reduced_vars and n_subset > 0:
        if comment:
            logger.info("Step %d", step)

        step += 1
        pik_subset_adjusted = pik_subset * (pik[non_integer_indices] / pik_star[non_integer_indices])
        pik_star_subset = _algo_fast_flight_cube(aux_subset, pik_subset_adjusted)
        pik_star[non_integer_indices] = pik_star_subset

        non_integer_indices = perm_order[(pik_star[perm_order] > EPS) & (pik_star[perm_order] < (1 - EPS))]
        pik_subset = pik_star[non_integer_indices]
        n_subset = len(pik_subset)

        if n_subset > 0:
            aux_subset = auxiliary_matrix[non_integer_indices, :]
            aux_subset = _reduce_matrix(aux_subset)
            n_reduced_vars = aux_subset.shape[1]
        else:
            n_reduced_vars = 0

    if comment:
        if step == 2:
            logger.info("NO FLIGHT PHASE")

    return pik_star


def landingcube(
    auxiliary_matrix: NDArray[np.floating],
    pik_star: NDArray[np.floating],
    pik: NDArray[np.floating],
    comment: bool = False,
) -> NDArray[np.floating]:
    """
    Landing phase of the cube method.
    Simplified implementation: use rounding with sample size adjustment.
    """
    non_integer_mask = (pik_star > EPS) & (pik_star < (1 - EPS))
    n_non_integer = np.sum(non_integer_mask)

    if n_non_integer == 0:
        return pik_star

    pik_final = pik_star.copy()
    pik_final = np.round(pik_final)

    target_size = int(np.round(pik.sum()))
    current_size = int(pik_final.sum())
    difference = target_size - current_size

    if difference > 0:
        candidates = np.where((pik_final == 0) & (pik_star > 0.5))[0]
        if len(candidates) > 0:
            add = np.random.choice(candidates, size=min(difference, len(candidates)), replace=False)
            pik_final[add] = 1
    elif difference < 0:
        candidates = np.where(pik_final == 1)[0]
        if len(candidates) > 0:
            remove = np.random.choice(candidates, size=min(-difference, len(candidates)), replace=False)
            pik_final[remove] = 0

    if comment:
        scaled_matrix = auxiliary_matrix[pik > EPS, :] / pik[pik > EPS, np.newaxis]
        ht_total = (scaled_matrix.T * pik[pik > EPS]).sum(axis=1)
        ht_estimate = (scaled_matrix.T * pik_final[pik > EPS]).sum(axis=1)
        relative_deviation = 100 * (ht_estimate - ht_total) / ht_total

        logger.info("QUALITY OF BALANCING:")
        for idx, (total, estimate, deviation) in enumerate(zip(ht_total, ht_estimate, relative_deviation)):
            logger.info("  Var %d: Total=%.4f, HT=%.4f, Dev=%.2f%%", idx + 1, total, estimate, deviation)

    return pik_final


def sample_cube(
    auxiliary_matrix: NDArray[np.floating],
    pik: NDArray[np.floating],
    order: int = 1,
    comment: bool = False,
    method: int = 1,
) -> NDArray[np.floating]:
    """
    Select a balanced sample using the cube method.
    Ported from R's sampling::sample_cube function.

    Args:
        auxiliary_matrix: Matrix of auxiliary variables for balancing (n_units x n_vars).
        pik: Vector of inclusion probabilities.
        order: 1=random order, 2=no change, 3=decreasing pik.
        comment: If True, print quality metrics.
        method: 1=flight+landing, 2=only flight (fast).

    Returns:
        Vector of 0/1 indicating selected units.
    """
    pik = np.asarray(pik, dtype=float)
    n_units = len(pik)

    if auxiliary_matrix.ndim == 1:
        auxiliary_matrix = auxiliary_matrix.reshape(n_units, -1)

    if method == 1:
        has_non_integer = np.any((pik > EPS) & (pik < (1 - EPS)))

        if has_non_integer:
            pik_star = fast_flight_cube(auxiliary_matrix, pik, order, comment)
        else:
            if comment:
                logger.info("NO FLIGHT PHASE")
            pik_star = pik.copy()

        has_non_integer_star = np.any((pik_star > EPS) & (pik_star < (1 - EPS)))

        if has_non_integer_star:
            pik_final = landingcube(auxiliary_matrix, pik_star, pik, comment)
        else:
            if comment:
                logger.info("NO LANDING PHASE")
            pik_final = pik_star

    else:
        n_vars = auxiliary_matrix.shape[1]
        pik_star = pik.copy()

        for i in range(n_vars):
            if np.any((pik_star > EPS) & (pik_star < (1 - EPS))):
                aux_subset = auxiliary_matrix[:, : (n_vars - i)] / pik[:, np.newaxis]
                pik_star = fast_flight_cube(aux_subset, pik_star, order, False)

        pik_final = pik_star.copy()
        for i in range(n_units):
            if np.random.random() < pik_final[i]:
                pik_final[i] = 1.0

    result = np.round(pik_final)

    if comment:
        scaled_matrix = auxiliary_matrix[pik > EPS, :] / pik[pik > EPS, np.newaxis]
        ht_total = (scaled_matrix.T * pik[pik > EPS]).sum(axis=1)
        ht_estimate = (scaled_matrix.T * result[pik > EPS]).sum(axis=1)
        relative_deviation = 100 * (ht_estimate - ht_total) / ht_total

        logger.info("\nQUALITY OF BALANCING")
        logger.info("%-30s %20s %20s", "TOTALS", "HT_ESTIMATORS", "REL_DEV")
        for total, estimate, deviation in zip(ht_total, ht_estimate, relative_deviation):
            logger.info("%-30.4f %20.4f %20.2f%%", total, estimate, deviation)

    return result


def sample_cube_stratified(
    auxiliary_matrix: NDArray[np.floating],
    pik: NDArray[np.floating],
    strata: NDArray[np.integer],
    order: int = 1,
    comment: bool = False,
) -> NDArray[np.floating]:
    """
    Stratified version of sample_cube.
    Applies the cube method within each stratum.
    Ported from R's sampling::samplecubestratified function.

    Args:
        auxiliary_matrix: Matrix of auxiliary variables (n_units x n_vars).
        pik: Vector of inclusion probabilities.
        strata: Vector of stratum labels (integers).
        order: Order for flight phase (1=random, 2=no change, 3=decreasing).
        comment: If True, print progress.

    Returns:
        Vector of 0/1 indicating selected units.
    """
    result = np.zeros_like(pik)

    unique_strata = np.unique(strata)

    for stratum in unique_strata:
        mask = strata == stratum
        indices = np.where(mask)[0]

        if len(indices) == 0:
            continue

        aux_stratum = auxiliary_matrix[mask, :]
        pik_stratum = pik[mask]

        result[indices] = sample_cube(aux_stratum, pik_stratum, order, comment)

    return result
