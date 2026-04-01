"""Centralized validation utilities for DataFusion.

This module provides reusable validation functions for DataFrames and other data structures.
"""

from __future__ import annotations

import pandas as pd


class DataValidationError(Exception):
    """Base exception for data validation errors."""

    pass


def require_columns(
    df: pd.DataFrame,
    cols: list[str],
    context: str = "",
    exc_type: type[Exception] = KeyError,
) -> None:
    """Validate that required columns exist in a DataFrame.

    Args:
        df: DataFrame to validate
        cols: List of required column names
        context: Optional context description for error messages
        exc_type: Exception type to raise (defaults to KeyError)
                  Use ValidationError from ceeb_bdot_merger.exceptions for custom errors

    Raises:
        exc_type: If any required columns are missing

    Examples:
        >>> require_columns(df, ["id", "name"])
        >>> require_columns(df, ["id"], "source data", KeyError)
    """
    missing = [c for c in cols if c not in df.columns]
    if missing:
        context_str = f" ({context})" if context else ""
        raise exc_type(f"Missing columns{context_str}: {missing}. Present columns: {list(df.columns)}")


def validate_dataframe_not_empty(df: pd.DataFrame, name: str = "DataFrame") -> None:
    """Validate that a DataFrame is not empty.

    Args:
        df: DataFrame to validate
        name: Name of the DataFrame for error messages

    Raises:
        DataValidationError: If the DataFrame is empty
    """
    if df.empty:
        raise DataValidationError(f"{name} is empty")


__all__ = [
    "DataValidationError",
    "require_columns",
    "validate_dataframe_not_empty",
]
