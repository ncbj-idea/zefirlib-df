import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------
# Helpers
# ---------------------------


def equal_or_nan_with_tolerance(a: pd.Series, b: pd.Series, tolerance: float) -> pd.Series:
    """Checks if series are in tolerance."""
    return a.notna() & b.notna() & ((a - b).abs() <= tolerance)


def print_summary_statistics(dataframe: pd.DataFrame) -> None:
    """Logs the shares (by count) and the shares by usable floor area (pow_uzytkowa_m2) for the selected flags."""
    if dataframe is None or dataframe.empty:
        logger.info("No data: DataFrame is empty.")
        return

    def share(column: str) -> float:
        if column not in dataframe.columns:
            logger.warning("Column %s does not exist – skipping share().", column)
            return np.nan
        number_of_rows = len(dataframe)
        return float(pd.Series(dataframe[column]).sum()) / float(number_of_rows) if number_of_rows else np.nan

    def weighted_share_by(column: str, weight: str = "pow_uzytkowa_m2") -> pd.Series:
        """
        Compute weighted shares of categories in a column, using a specified
        weight variable. Returns the share of total weight for each category.

        Args:
            column : categorical variable to summarize.
            weight : column containing numeric weights.

        Returns:
            Weighted shares indexed by category.
        """
        if column not in dataframe.columns:
            logger.warning("weighted_share_by: column %s does not exist – skipping.", column)
            return pd.Series(dtype=float)
        if weight not in dataframe.columns:
            logger.warning("weighted_share_by: weight column %s does not exist – skipping.", weight)
            return pd.Series(dtype=float)

        total_weight = dataframe[weight].sum()
        if not np.isfinite(total_weight) or total_weight == 0:
            logger.warning("weighted_share_by: total weight in %s is 0/NaN – skipping.", weight)
            return pd.Series(dtype=float)

        grouped = dataframe.groupby(column, dropna=False)[weight].sum()
        shares = grouped / total_weight

        idx = shares.index
        type_counts = pd.Series([type(x).__name__ for x in idx]).value_counts().to_dict()
        sample = list(idx[:20])
        logger.error(
            "DEBUG weighted_share_by: column=%s | index_types=%s | sample_index=%s",
            column,
            type_counts,
            sample,
        )

        return shares.sort_index()

    def log_one(column: str) -> None:
        try:
            ratio = share(column)
            weighted_shares = weighted_share_by(column)
        except Exception:
            if column in dataframe.columns:
                col = dataframe[column]
                val_types = col.map(lambda x: type(x).__name__).value_counts().to_dict()
                uniques = col.dropna().unique()[:30]
                logger.exception(
                    "CRASH for column=%s | dtype=%s | value_types=%s | sample_uniques=%s",
                    column,
                    col.dtype,
                    val_types,
                    list(uniques),
                )
            raise

        logger.info(
            "Share (in numbers) %s == True: %.2f%%",
            column,
            (ratio if pd.notna(ratio) else 0.0) * 100.0,
        )
        if not weighted_shares.empty:
            text = weighted_shares.apply(lambda value: f"{value:.2%}").to_string()
            logger.info("Shares by area (pow_uzytkowa_m2) in %s:\n%s", column, text)

    for column in ("heat_connected", "gas_connected"):
        log_one(column)
