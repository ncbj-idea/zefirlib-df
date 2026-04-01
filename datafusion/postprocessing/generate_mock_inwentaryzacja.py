from __future__ import annotations

import argparse
import logging
import random
import subprocess
from pathlib import Path

import pandas as pd

from datafusion.constants import TABLE_BUILDING_INVENTORY

_logger = logging.getLogger(__name__)


DACH_VALUES = ["PO REMONCIE", "NOWY", "STARY", ""]
DACH_WEIGHTS = [0.50, 0.10, 0.05, 0.35]

OKNA_VALUES = ["LATA 90-TE", "PO 2000", "NOWE WT21", ""]
OKNA_WEIGHTS = [0.45, 0.25, 0.05, 0.25]

WIEK_VALUES = ["po 1950r.", "po 1990r.", "stary", "Nowy po 2010r", ""]
WIEK_WEIGHTS = [0.25, 0.40, 0.10, 0.05, 0.20]

OCIEPLENIE_VALUES = ["0-8CM", "8-15 CM", "BRAK", ""]
OCIEPLENIE_WEIGHTS = [0.40, 0.15, 0.25, 0.20]

UWAGI_VALUES = ["skos", "biur", ""]
UWAGI_WEIGHTS = [0.10, 0.02, 0.88]


def generate_mock_values() -> dict[str, str]:
    """Generate random mock values for manual check columns."""
    return {
        "Dach": random.choices(DACH_VALUES, weights=DACH_WEIGHTS, k=1)[0],
        "Okna": random.choices(OKNA_VALUES, weights=OKNA_WEIGHTS, k=1)[0],
        "Wiek_budynku_p_modern": random.choices(WIEK_VALUES, weights=WIEK_WEIGHTS, k=1)[0],
        "Ocieplenie_ścian": random.choices(OCIEPLENIE_VALUES, weights=OCIEPLENIE_WEIGHTS, k=1)[0],
        "Uwagi": random.choices(UWAGI_VALUES, weights=UWAGI_WEIGHTS, k=1)[0],
        "Zrobione": "Zrobione",
        "street_view": "",
    }


def _load_inventory_from_db(container_name: str = "datafusion-db") -> pd.DataFrame:
    """Load building_inventory table from database using docker exec."""
    cmd = [
        "docker",
        "exec",
        container_name,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-t",
        "-c",
        f"SELECT * FROM {TABLE_BUILDING_INVENTORY};",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        raise RuntimeError(f"Failed to load data: {result.stderr}")

    if not result.stdout.strip():
        return pd.DataFrame()

    from io import StringIO

    df = pd.read_csv(StringIO(result.stdout), sep="|", header=None, skipinitialspace=True)

    df.columns = [
        "merged_id",
        "ulica",
        "numer_porzadkowy",
        "geom_wkt",
        "nazwa_funkcji_ogolnej",
        "przydzial",
        "Dach",
        "Okna",
        "Wiek_budynku_p_modern",
        "Ocieplenie_ścian",
        "Uwagi",
        "Zrobione",
        "street_view",
    ]

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()

    return df[["merged_id", "ulica", "numer_porzadkowy", "geom_wkt", "nazwa_funkcji_ogolnej", "przydzial"]]


def generate_mock_inwentaryzacja(output_path: Path, seed: int | None = None) -> pd.DataFrame:
    """Generate mock manual check data from building_inventory table."""
    if seed is not None:
        random.seed(seed)

    _logger.info("Loading data from %s", TABLE_BUILDING_INVENTORY)

    inventory_df = _load_inventory_from_db()

    if inventory_df.empty:
        _logger.warning("building_inventory is empty, nothing to process")
        return pd.DataFrame()

    _logger.info("Loaded %d records from building_inventory", len(inventory_df))

    result_rows = []
    for _, row in inventory_df.iterrows():
        row_dict = {
            "id": row["merged_id"],
            "ulica": row["ulica"],
            "numer_porzadkowy": row["numer_porzadkowy"],
            "geom_wkt": row["geom_wkt"],
            "nazwa_funkcji_ogolnej": row["nazwa_funkcji_ogolnej"],
        }

        mock_values = generate_mock_values()
        row_dict.update(mock_values)
        row_dict["przydzial"] = row.get("przydzial", "")

        result_rows.append(row_dict)

    result_df = pd.DataFrame(result_rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_excel(output_path, index=False, engine="openpyxl")
    _logger.info("Saved mock inwentaryzacja to %s", output_path)

    return result_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate mock manual check result from building_inventory table")
    parser.add_argument(
        "output_path",
        type=Path,
        help="Output excel file path (e.g., input/0207011/postprocessing/inventory_files/inwentaryzacja_mock.xlsx)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--container",
        type=str,
        default="datafusion-db",
        help="Docker container name for database",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    generate_mock_inwentaryzacja(args.output_path, args.seed)


if __name__ == "__main__":
    main()
