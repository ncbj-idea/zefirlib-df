import re

import pandas as pd
import pytest

from datafusion.utils.utils import validate_dataframe_by_schema


def test_validate_dataframe_by_schema_missing_column() -> None:
    df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
    expected_schema = {"object": ["C", "D"]}

    with pytest.raises(ValueError, match=re.escape("Required column C not found in DataFrame")):
        validate_dataframe_by_schema(df, expected_schema)


def test_validate_dataframe_by_schema_wrong_data_type() -> None:
    df = pd.DataFrame({"A": [1, 2, 3], "B": ["4", "5", "6"]})
    expected_schema = {"object": ["A", "B"]}

    with pytest.raises(
        ValueError,
        match=re.escape("Column 'A' is not of type 'object' (found type: int64)"),
    ):
        validate_dataframe_by_schema(df, expected_schema)


def test_validate_dataframe_by_schema_multiple_columns_same_type() -> None:
    df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6], "C": [True, False, True]})
    expected_schema = {"bool": ["A", "C"]}

    with pytest.raises(
        ValueError,
        match=re.escape("Column 'A' is not of type 'bool' (found type: int64)"),
    ):
        validate_dataframe_by_schema(df, expected_schema)


def test_validate_dataframe_by_schema_single_required_column() -> None:
    df = pd.DataFrame({"B": [1, 2, 3]})
    expected_schema = {"object": ["A"]}

    with pytest.raises(ValueError, match=re.escape("Required column A not found in DataFrame")):
        validate_dataframe_by_schema(df, expected_schema)


def test_validate_dataframe_by_schema_valid_dataframe() -> None:
    df = pd.DataFrame(
        {
            "A": [1, 2, 3],
            "B": [4.5, 5.6, 6.7],
            "C": [True, False, True],
            "D": [10, 20, 30],
        }
    )
    expected_schema = {
        "bool": ["C"],
        "float64": ["B"],
        "int64": ["A", "D"],
    }

    validate_dataframe_by_schema(df, expected_schema)
