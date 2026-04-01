from pathlib import Path

import pandas as pd
import yaml

# ---------------------------
# Config
# ---------------------------


def load_config(path: Path | str) -> dict:
    """
    Load YAML configuration.

    Args:
        path : Path to yaml config

    Return:
        Dict : yaml config
    """
    config_path = Path(path).expanduser().resolve()
    with open(config_path, encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


# ---------------------------
# Normalize to lowercase names of column
# ---------------------------


def normalize_col_names_lower(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = pd.Index(df.columns).map(lambda c: str(c).replace("\u00a0", " ").strip().lower())
    return df


__all__ = [
    "load_config",
    "normalize_col_names_lower",
]
