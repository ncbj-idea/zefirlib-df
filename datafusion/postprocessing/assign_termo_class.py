from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

from datafusion import get_resource_path
from datafusion.configs.postprocessing_config import PostprocessingConfig
from datafusion.constants import TABLE_BUILDING_INVENTORY, TABLE_SAMPLED_BUILDINGS
from datafusion.postprocessing.helpers.helpers_assign_termo import (
    apply_termo_scoring,
    attach_termo_flags,
    ensure_all_blank_ids_done,
    get_demand_data,
    join_evaluation_and_scores,
    left_join_sample_features,
    log_missing_patterns,
    log_termo_summary,
    normalize_col_names,
    normalize_merged_id,
    post_adjustments_and_join_demand,
    trim_whitespace,
)
from datafusion.postprocessing.helpers.vim_knn import vim_knn_impute
from datafusion.utils.crud import load_dataframe_from_db, save_dataframe_to_db
from datafusion.utils.validation import require_columns

logger = logging.getLogger(__name__)


# ---------------------------
# I/O
# ---------------------------


def read_inputs_assign(
    base_directory: Path, engine: Engine
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Reads input needed in assign_termo part.
    Returns:
      inventory_df, random_sample_df, demand_df, blank_inventory_df
    """

    # Use hardcoded demand data instead of reading from Excel
    demand = get_demand_data()

    inventory_directory = (base_directory / "inventory_files").resolve()

    blank_inventory = load_dataframe_from_db(engine, TABLE_BUILDING_INVENTORY)
    random_sample = load_dataframe_from_db(engine, TABLE_SAMPLED_BUILDINGS)

    if blank_inventory.empty:
        raise ValueError("Inventory is empty")

    if random_sample.empty:
        raise ValueError("Wylosowane is empty")

    key_columns = [
        "id",
        "merged_id",
        "Rodzaj_budynku",
        "Ocieplenie_ścian",
        "Okna",
        "Dach",
        "Wiek_budynku_p_modern",
    ]
    blank_inventory = trim_whitespace(
        blank_inventory,
        [column for column in key_columns if column in blank_inventory.columns],
    )
    random_sample = trim_whitespace(
        random_sample,
        [column for column in key_columns if column in random_sample.columns],
    )
    demand = trim_whitespace(
        demand,
        [column for column in key_columns if column in demand.columns],
    )

    inventory_files: list[Path] = sorted(
        (path for path in inventory_directory.glob("*.xlsx") if path.is_file()),
        key=lambda path: path.name.lower(),
    )
    if not inventory_files:
        raise FileNotFoundError(f"No personal inventory files (*.xlsx) in: {inventory_directory}")

    inventory_parts: list[pd.DataFrame] = []
    for file_path in inventory_files:
        part_dataframe = pd.read_excel(file_path, engine="openpyxl")
        part_dataframe = trim_whitespace(
            part_dataframe,
            [column for column in key_columns if column in part_dataframe.columns],
        )
        if "Zrobione" in part_dataframe.columns:
            part_dataframe = part_dataframe[~part_dataframe["Zrobione"].isna()].copy()
        if not part_dataframe.empty:
            inventory_parts.append(part_dataframe)

    if inventory_parts:
        inventory = pd.concat(inventory_parts, ignore_index=True, copy=False)
    else:
        raise ValueError(f"All personal inventory files in {inventory_directory} are empty or have no 'Zrobione' rows.")

    inventory = trim_whitespace(inventory, [column for column in key_columns if column in inventory.columns])

    if "id" in inventory.columns:
        inventory = inventory.drop_duplicates(subset=["id"], keep="first").copy()

    inventory = inventory.drop(columns=["street_view"], errors="ignore")

    if inventory.empty:
        raise ValueError(f"Merged inventory is empty after cleaning in folder: {inventory_directory}")

    rs = set(random_sample["merged_id"].dropna().astype(str))
    bi = (
        set(blank_inventory["merged_id"].dropna().astype(str))
        if "merged_id" in blank_inventory.columns
        else set(blank_inventory["id"].dropna().astype(str))
    )
    inv = (
        set(inventory["id"].dropna().astype(str))
        if "id" in inventory.columns
        else set(inventory["merged_id"].dropna().astype(str))
    )

    logger.warning(
        "Unique merged_id counts: blank_inventory=%d, random_sample=%d, inventory_folder=%d",
        len(bi),
        len(rs),
        len(inv),
    )
    logger.warning("Overlap: random_sample ∩ blank_inventory = %d", len(rs & bi))
    logger.warning("Overlap: random_sample ∩ inventory_folder = %d", len(rs & inv))
    logger.warning(
        "Done coverage (inventory_folder vs random_sample): %.2f%%",
        100.0 * len(rs & inv) / max(1, len(rs)),
    )

    if "rodzaj_budynku" in random_sample.columns:
        random_sample = random_sample.rename(columns={"rodzaj_budynku": "Rodzaj_budynku"})

    if "rodzaj_budynku" in inventory.columns:
        inventory = inventory.rename(columns={"rodzaj_budynku": "Rodzaj_budynku"})

    # Standardize building types to lowercase and stripped
    if "Rodzaj_budynku" in random_sample.columns:
        random_sample["Rodzaj_budynku"] = random_sample["Rodzaj_budynku"].astype(str).str.strip().str.lower()
    if "Rodzaj_budynku" in inventory.columns:
        inventory["Rodzaj_budynku"] = inventory["Rodzaj_budynku"].astype(str).str.strip().str.lower()

    # Normalize IDs to handle Excel numeric formatting (e.g. 123.0 -> "123")
    if "id" in inventory.columns:
        inventory["id"] = normalize_merged_id(inventory["id"])
    if "merged_id" in inventory.columns:
        inventory["merged_id"] = normalize_merged_id(inventory["merged_id"])

    if "id" in blank_inventory.columns:
        blank_inventory["id"] = normalize_merged_id(blank_inventory["id"])
    if "merged_id" in blank_inventory.columns:
        blank_inventory["merged_id"] = normalize_merged_id(blank_inventory["merged_id"])

    if "merged_id" in random_sample.columns:
        random_sample["merged_id"] = normalize_merged_id(random_sample["merged_id"])

    blank_inventory = normalize_col_names(blank_inventory)
    random_sample = normalize_col_names(random_sample)
    inventory = normalize_col_names(inventory)
    demand = normalize_col_names(demand)

    return (inventory, random_sample, demand, blank_inventory)


# ---------------------------
# Evaluation (termo_eval + rate)
# ---------------------------


def load_evaluation_tables(
    base_directory: Path,
    inventory_type: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load Excel sheets from (input)/'punktacja_termo.xlsx'

    - thermal_evaluation: sheet = inventory_type (e.g. 'Stara_inwentaryzacja')
    - scoring           : sheet = 'punktacja'
    - roof_scoring_table: filtered + first column renamed to 'Dach'
    - age_scoring_table : filtered + first column renamed to 'Wiek_budynku_p_modern'
    """
    evaluation_workbook_path = get_resource_path("punktacja_termo.xlsx")
    if not evaluation_workbook_path.exists():
        raise FileNotFoundError(f"Evaluation workbook not found: {evaluation_workbook_path}")

    logger.info("Reading evaluation workbook: %s", evaluation_workbook_path)

    thermal_evaluation = pd.read_excel(evaluation_workbook_path, sheet_name=inventory_type, engine="openpyxl")
    scoring = pd.read_excel(evaluation_workbook_path, sheet_name="punktacja", engine="openpyxl")

    if thermal_evaluation.empty:
        raise ValueError(f"Thermal evaluation sheet '{inventory_type}' is empty in: {evaluation_workbook_path}")
    if scoring.empty:
        raise ValueError(f"Sheet 'punktacja' is empty in: {evaluation_workbook_path}")

    evaluation_columns = [
        "Rodzaj_budynku",
        "Ocieplenie_ścian",
        "Okna",
        "Dach",
        "Wiek_budynku_p_modern",
        "Parameter",
    ]
    thermal_evaluation = trim_whitespace(
        thermal_evaluation,
        [column for column in evaluation_columns if column in thermal_evaluation.columns],
    )
    scoring = trim_whitespace(
        scoring,
        [column for column in evaluation_columns if column in scoring.columns],
    )

    thermal_evaluation = thermal_evaluation.drop(columns=["Klasa"], errors="ignore")

    if "Parameter" not in scoring.columns:
        raise ValueError("Sheet 'punktacja' must contain a 'Parameter' column.")

    roof_scoring_table = scoring.loc[scoring["Parameter"] == "Dach"].copy()
    roof_scoring_table = roof_scoring_table.drop(columns=["Parameter"], errors="ignore")
    if roof_scoring_table.empty:
        raise ValueError("Table 'roof_scoring_table' is empty (no rows with Parameter == 'Dach').")
    first_column = roof_scoring_table.columns[0]
    roof_scoring_table = roof_scoring_table.rename(columns={first_column: "Dach"})

    age_scoring_table = scoring.loc[scoring["Parameter"] == "Wiek_budynku_p_modern"].copy()
    age_scoring_table = age_scoring_table.drop(columns=["Parameter"], errors="ignore")
    if age_scoring_table.empty:
        raise ValueError("Table 'age_scoring_table' is empty (no rows with Parameter == 'Wiek_budynku_p_modern').")
    first_column = age_scoring_table.columns[0]
    age_scoring_table = age_scoring_table.rename(columns={first_column: "Wiek_budynku_p_modern"})

    roof_scoring_table = trim_whitespace(
        roof_scoring_table,
        (["Rodzaj_budynku", "Dach"] if {"Rodzaj_budynku", "Dach"}.issubset(roof_scoring_table.columns) else None),
    )
    age_scoring_table = trim_whitespace(
        age_scoring_table,
        (
            ["Rodzaj_budynku", "Wiek_budynku_p_modern"]
            if {"Rodzaj_budynku", "Wiek_budynku_p_modern"}.issubset(age_scoring_table.columns)
            else None
        ),
    )

    logger.info(
        "Loaded tables: thermal_evaluation=%d, scoring=%d, roof_scoring=%d, age_scoring=%d",
        len(thermal_evaluation),
        len(scoring),
        len(roof_scoring_table),
        len(age_scoring_table),
    )

    return thermal_evaluation, scoring, roof_scoring_table, age_scoring_table


# =============================================================================
# Orchestration
# =============================================================================


def run_assign_termo_class(
    base_directory: Path,
    engine: Engine,
    config: PostprocessingConfig,
) -> None:
    """
    Runner of assign_termo_class.

    Args:
        base_directory : Path, Base directory with city-specific inputs/outputs.
        config : PostprocessingConfig instance.

    Returns:
        None, saves estimation and updated inventory to Excel files and logs summaries.

    """
    logger.info("Starting assign termo for city.")
    inventory_type = str(config.params.inventory_type)

    distinct_variables = [
        "pow_uzytkowa_m2",
        "longitude_centroid",
        "latitude_centroid",
        "Rodzaj_budynku",
    ]
    imputation_variables = distinct_variables + [
        "Dach",
        "Okna",
        "Wiek_budynku_p_modern",
        "Ocieplenie_ścian",
    ]

    (
        inventory,
        random_sample,
        demand,
        blank_inventory,
    ) = read_inputs_assign(base_directory, engine)

    ensure_all_blank_ids_done(blank_inventory, inventory)
    require_columns(
        random_sample,
        ["merged_id", "Rodzaj_budynku"],
        context="run_assign_termo_class: random_sample merge",
    )

    inventory = left_join_sample_features(inventory, random_sample, distinct_variables)

    # Diagnostic check after join
    nan_counts = inventory[distinct_variables].isna().sum()
    logger.info("NaN counts after left_join_sample_features:\n%s", nan_counts)

    require_columns(
        inventory,
        imputation_variables,
        context="run_assign_termo_class: imputation_variables",
    )

    imputation_seed = int(config.params.seed_imputation)
    logger.info("Starting vim_knn_impute for variables: %s", imputation_variables)
    inventory[imputation_variables] = vim_knn_impute(
        inventory[imputation_variables],
        variables=imputation_variables,
        k=10,
        distance_variables=imputation_variables,
        weight_mode="one_minus_distance",
        seed=imputation_seed,
        tie_break="deterministic",
    )
    logger.info("Finished vim_knn_impute. NaN counts:\n%s", inventory[imputation_variables].isna().sum())

    inventory = attach_termo_flags(inventory)

    (
        thermal_evaluation,
        _,
        roof_scoring_table,
        age_scoring_table,
    ) = load_evaluation_tables(base_directory, inventory_type)

    inventory = join_evaluation_and_scores(inventory, thermal_evaluation, roof_scoring_table, age_scoring_table)

    inventory = apply_termo_scoring(
        inventory,
        thermal_evaluation,
        roof_scoring_table,
        age_scoring_table,
        building_type_column="Rodzaj_budynku",
        roof_column="Dach",
        age_column="Wiek_budynku_p_modern",
        promotion_column="Awans",
        score_column="Punktacja_termo",
    )

    inventory = post_adjustments_and_join_demand(inventory, demand)
    logger.info(
        "Finished post_adjustments_and_join_demand. NaN counts for demand columns (heat, cold, heat_water):\n%s",
        inventory[["heat", "cold", "heat_water"]].isna().sum(),
    )

    print("inventory.head()")
    print(inventory.head())

    selected_columns = [
        "merged_id",
        "Rodzaj_budynku",
        "Klasa_termo",
        "Wiek_budynku_p_modern",
        "heat",
        "cold",
        "heat_water",
        "klima",
    ]
    columns_to_join = [column for column in selected_columns if column in inventory.columns]
    missing_inventory_columns = [column for column in selected_columns if column not in inventory.columns]
    if missing_inventory_columns:
        logger.warning(
            "Some columns for estimation are missing in inventory: %s",
            missing_inventory_columns,
        )

    sample_for_estimation = random_sample.merge(
        inventory[columns_to_join],
        on=["merged_id", "Rodzaj_budynku"],
        how="left",
    )

    # Diagnostic: check overlap with inventory
    matched_estimation = sample_for_estimation["Klasa_termo"].notna().sum()
    logger.info(
        "Final sample_for_estimation (data_to_estimation) size: %d. Matches with inventory: %d (%.2f%%)",
        len(sample_for_estimation),
        matched_estimation,
        100.0 * matched_estimation / max(1, len(sample_for_estimation)),
    )

    save_dataframe_to_db(engine, sample_for_estimation, "data_to_estimation")
    save_dataframe_to_db(engine, inventory, "termo_inwentaryzacja")
    logger.info("Saved estimation and termo_inwentaryzacja to database")

    log_termo_summary(inventory)
    log_missing_patterns(inventory)

    logger.info("Finished assign termo for city.")
