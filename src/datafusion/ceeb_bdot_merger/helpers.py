"""Helper utilities for BDOT modification functions.

Small, well-tested helpers live here so higher-level modules remain focused.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from datafusion.utils.validation import require_columns

from .exceptions import ValidationError


def _to_bool_series(s: pd.Series) -> pd.Series:
    """Convert pandas Series to boolean Series.

    Handles various input formats and converts them to boolean values.
    """
    if s.dtype == bool:
        return s
    try:
        return s.astype(float) == 1.0
    except Exception:
        return s.astype(str).str.lower().isin(["true", "1", "t", "y", "yes"])


def _validate_dataframe_not_empty(df: pd.DataFrame, name: str = "DataFrame") -> None:
    """Validate that a DataFrame is not empty.

    Raises ValidationError if empty.
    """
    if df.empty:
        raise ValidationError(f"{name} is empty")


def _validate_columns_exist(df: pd.DataFrame, columns: Iterable[str], context: str = "") -> None:
    """Validate that required columns exist in DataFrame.

    Raises ValidationError listing missing columns if any are absent.
    """
    require_columns(df, list(columns), context, ValidationError)


def _validate_coordinate_system(crs: str) -> None:
    """Validate coordinate system format (very lightweight check)."""
    if not crs or not isinstance(crs, str):
        raise ValidationError(f"Invalid coordinate system: {crs}")
    if not crs.upper().startswith("EPSG:"):
        # Not critical: just a warning-level observation in original code, but we raise
        # ValidationError only for clearly invalid input.
        pass


def _create_address_key(street: pd.Series, number: pd.Series) -> pd.Series:
    """Create address key by combining street and number."""
    return street.astype(str) + "_" + number.astype(str)


__all__ = [
    "_to_bool_series",
    "_validate_dataframe_not_empty",
    "_validate_columns_exist",
    "_validate_coordinate_system",
    "_create_address_key",
]


def _optimize_string_columns_to_categorical(
    df: pd.DataFrame, columns: list[str] = None, cardinality_threshold: float = 0.5
) -> pd.DataFrame:
    """Convert low-cardinality string columns to categorical dtype for memory optimization.

    This is a lightweight port of the original helper so pipeline can import it
    without depending on the monolithic module.
    """
    if columns is None:
        columns = df.select_dtypes(include=["object", "string"]).columns.tolist()

    for col in columns:
        if col not in df.columns:
            continue

        total = len(df[col])
        if total == 0:
            continue

        unique = df[col].nunique()
        cardinality = unique / total

        if cardinality < cardinality_threshold:
            try:
                df[col] = df[col].astype("category")
            except Exception:
                # Best-effort conversion, ignore failures
                pass

    return df
