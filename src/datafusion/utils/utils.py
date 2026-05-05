import csv
import json
from pathlib import Path

import pandas as pd

TRUE_VALUES = ["Tak"]
FALSE_VALUES = ["Nie"]

BOOLEAN_COLUMNS = ["C.W.U.", "C.O."]
POSSIBLE_STRING_COLUMNS = [
    "Ulica",
    "Numer budynku",
    "Numer domu",
    "Źródło ciepła",
    "Rodzaj budynku A",
    "Klasa kotła",
    "Typ deklaracji",
]
EXPECTED_CEEB_DATA_SCHEMA: dict[str, dict[str, list[str]]] = {
    "ceeb_devices": {
        "object": [
            "Ulica",
            "Numer budynku",
            "Źródło ciepła",
            "Rodzaj budynku A",
            "Typ deklaracji",
        ],
        "float64": [
            "Liczba eksploatowanych źródeł ciepła",
            "Liczba zainstalowanych źródeł ciepła",
        ],
        "bool": BOOLEAN_COLUMNS,
    },
    "ceeb_classes": {
        "object": [
            "Ulica",
            "Numer domu",
            "Klasa kotła",
            "Typ deklaracji",
        ]
    },
}


def read_json(file: Path) -> dict[str, str]:
    with open(file) as f:
        return json.load(f)


def validate_dataframe_by_schema(df: pd.DataFrame, expected_schema: dict[str, list[str]]) -> None:
    """
    Validates that the DataFrame contains the specified columns with the correct data types.

    Args:
        df (pd.DataFrame): The DataFrame to validate.
        expected_schema (Dict[str, List[str]]): A dictionary where each key is a data type
            (as a string, e.g., 'object', 'int64') and each value is a list of column names
            expected to have that data type.a
    Raises:
        ValueError: If any required column is missing from the DataFrame or if a column's data type
            does not match the expected data type.
    """
    for expected_type, columns in expected_schema.items():
        if isinstance(columns, str):
            columns = [columns]
        for col in columns:
            if col not in df.columns:
                raise ValueError(f"Required column {col} not found in DataFrame")
            # Allow pandas nullable boolean dtype as well when 'bool' is expected
            if expected_type == "bool":
                if not pd.api.types.is_bool_dtype(df[col].dtype):
                    raise ValueError(f"Column '{col}' is not of type '{expected_type}' (found type: {df[col].dtype})")
            else:
                if not pd.api.types.is_dtype_equal(df[col].dtype, expected_type):
                    raise ValueError(f"Column '{col}' is not of type '{expected_type}' (found type: {df[col].dtype})")


def find_delimiter(file_path: str | Path):
    """Return delimiter detected by csv.Sniffer or None.

    Raises a clearer PermissionError if the file cannot be opened due to
    OS permissions (common when bind-mounting host files into Docker).
    """
    file_path_str = str(file_path)
    try:
        with open(file_path_str, newline="") as file:
            # Read up to 10 lines safely; handle files with fewer lines without raising StopIteration
            sample_lines = []
            for _ in range(10):
                line = file.readline()
                if not line:
                    break
                sample_lines.append(line)
            sample = "".join(sample_lines)
            # keep previous behavior of printing a small sample for debugging
            print("Sample:\n", sample)
            file.seek(0)

            if not sample:
                # Empty file — nothing to sniff
                return None

            try:
                dialect = csv.Sniffer().sniff(sample)
                print(dialect.delimiter)
                return dialect.delimiter
            except csv.Error:
                return None
    except PermissionError as exc:
        # Raise a friendlier error message to help debugging permission issues
        raise PermissionError(
            f"Permission denied when opening '{file_path_str}'.\n"
            "If this file is a host-mounted volume in Docker, ensure the container user\n"
            "has read access. For local development you can either: (1) set HOST_UID/HOST_GID\n"
            "in a .env used by docker-compose so the container runs as your user, or (2)\n"
            "adjust ownership/permissions on the host (e.g. `chown 1321:1321 ./input` or `chmod a+r ./input`)."
        ) from exc
