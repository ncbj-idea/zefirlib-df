import logging

import numpy as np
import pandas as pd

from datafusion.utils.validation import require_columns

logger = logging.getLogger(__name__)


# ---------------------------
# Helpers
# ---------------------------


def trim_whitespace(dataframe: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """
    Trim surrounding whitespace in selected text columns, converting empty
    results to NA and normalizing non-breaking spaces.

    Args:
        dataframe : Input data.
        columns : Columns to clean; if None, all text columns are used.

    Returns:
        Copy of the data with cleaned text columns.
    """
    output = dataframe.copy()

    def is_text_column(series: pd.Series) -> bool:
        return pd.api.types.is_string_dtype(series) or series.dtype == "object"

    if columns is None:
        columns = [column for column in output.columns if is_text_column(output[column])]
    else:
        columns = [column for column in columns if column in output.columns and is_text_column(output[column])]

    for column in columns:
        series = output[column].astype("string")
        series = series.str.replace("\u00a0", " ", regex=False).str.strip()
        series = series.where(series.ne(""), pd.NA)
        output[column] = series

    return output


def ensure_all_blank_ids_done(
    blank_inventory: pd.DataFrame,
    inventory: pd.DataFrame,
    *,
    max_show: int = 50,
) -> None:
    """
    Verify that all IDs listed in the blank inventory appear in the completed
    inventory. Raises an error if any IDs are missing.

    Args:
        blank_inventory : Source list of required IDs.
        inventory : Completed inventory expected to contain all IDs.
        max_show : Maximum number of missing IDs to display in the error.

    Returns:
        None
    """
    if blank_inventory.empty:
        logger.warning("Blank inventory DataFrame is empty in ensure_all_blank_ids_done – skipping completeness check.")
        return

    if "id" not in blank_inventory.columns:
        logger.warning("Blank inventory has no 'id' column — skipping completeness check.")
        return

    if "id" in inventory.columns:
        completed_ids = set(inventory["id"].dropna().astype(str))
    elif "merged_id" in inventory.columns:
        completed_ids = set(inventory["merged_id"].dropna().astype(str))
    else:
        raise ValueError("Finished inventory lacks 'id' or 'merged_id' column.")

    blank_ids = blank_inventory["id"].dropna().astype(str).tolist()
    missing_ids = [identifier for identifier in blank_ids if identifier not in completed_ids]

    if missing_ids:
        count_missing = len(missing_ids)
        head = ", ".join(missing_ids[:max_show])
        tail_note = f" (and {count_missing - max_show} more)" if count_missing > max_show else ""
        raise RuntimeError(
            "Some buildings from the blank inventory are missing in the finished "
            f"inventory! Missing count={count_missing}. Example IDs: {head}{tail_note}"
        )


def distinct_keep_first(dataframe: pd.DataFrame, key_column: str) -> pd.DataFrame:
    require_columns(dataframe, [key_column], context="distinct_keep_first")
    return dataframe[~dataframe[key_column].duplicated(keep="first")].copy()


def left_join_sample_features(
    inventory: pd.DataFrame,
    random_sample: pd.DataFrame,
    distinct_variables: list[str],
) -> pd.DataFrame:
    """
    Left-join selected distinct variables from a sampled dataset onto the
    inventory using the 'merged_id' key.

    Args:
        inventory : Full inventory to enrich.
        random_sample : Dataset containing sampled units.
        distinct_variables : Variables to bring from the sample.

    Returns:
        Inventory with joined sample-derived variables.
    """
    if inventory.empty:
        logger.warning("left_join_sample_features: inventory is empty.")
        return inventory.copy()
    if random_sample.empty:
        logger.warning("left_join_sample_features: random_sample is empty.")
        return inventory.copy()

    require_columns(random_sample, ["merged_id"], context="left_join_sample_features(random_sample)")

    # Identify which variables are actually present in the sample
    vars_to_join = [variable for variable in distinct_variables if variable in random_sample.columns]

    if not vars_to_join:
        logger.warning("left_join_sample_features: none of distinct_variables present in random_sample.")
        return inventory.copy()

    # CRITICAL: Drop these columns from inventory if they already exist
    # to avoid _x/_y suffixes and ensure we use the filled data from the sample
    inventory_copy = inventory.copy()
    columns_to_drop = [variable for variable in vars_to_join if variable in inventory_copy.columns]
    if columns_to_drop:
        logger.info("Dropping existing columns from inventory before join: %s", columns_to_drop)
        inventory_copy = inventory_copy.drop(columns=columns_to_drop)

    # Rename ID if necessary
    if "id" in inventory_copy.columns and "merged_id" not in inventory_copy.columns:
        inventory_copy = inventory_copy.rename(columns={"id": "merged_id"})

    if "merged_id" not in inventory_copy.columns:
        raise ValueError("Inventory dataframe must contain 'merged_id' or 'id' after rename.")

    # Prepare sample part to join
    sample_to_join = random_sample[["merged_id"] + vars_to_join].copy()
    sample_to_join = distinct_keep_first(sample_to_join, "merged_id")

    # Perform the merge
    output = inventory_copy.merge(sample_to_join, on="merged_id", how="left")

    # Log diagnostics
    matched_count = output[vars_to_join[0]].notna().sum() if vars_to_join else 0
    logger.info("Join result: %d/%d rows matched with random_sample features", matched_count, len(output))

    return output


def join_evaluation_and_scores(
    inventory: pd.DataFrame,
    thermal_evaluation: pd.DataFrame,
    roof_scoring_table: pd.DataFrame,
    age_scoring_table: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join inventory with thermal_evaluation by
    ('Ocieplenie_ścian','Okna','Rodzaj_budynku').

    Args :
        inventory : DataFrame with inventory.
        thermal_evaloution : DatFrame with thermal evaluation.

    Returns:
        DataFrame, merged inventory and thermal evalution.
    """
    required_inventory_columns = [
        "Rodzaj_budynku",
        "Ocieplenie_ścian",
        "Okna",
    ]
    require_columns(
        inventory,
        required_inventory_columns,
        context="join_evaluation_and_scores(inventory)",
    )

    require_columns(
        thermal_evaluation,
        ["Ocieplenie_ścian", "Okna", "Rodzaj_budynku"],
        context="join_evaluation_and_scores(thermal_evaluation)",
    )

    output = inventory.merge(
        thermal_evaluation,
        on=["Ocieplenie_ścian", "Okna", "Rodzaj_budynku"],
        how="left",
    )
    return output


def apply_termo_scoring(
    inventory: pd.DataFrame,
    thermal_evaluation: pd.DataFrame,
    roof_scoring_table: pd.DataFrame,
    age_scoring_table: pd.DataFrame,
    *,
    building_type_column: str = "Rodzaj_budynku",
    roof_column: str = "Dach",
    age_column: str = "Wiek_budynku_p_modern",
    promotion_column: str = "Awans",
    score_column: str = "Punktacja_termo",
) -> pd.DataFrame:
    """
    Compute add_points from 'Scoring*' columns and final_points based on Awans.
    Map final_points (1..6) to classes F..A.

    Args :
        inventory : DataFrame with inventory.
        roof_scoring_table : table with roof scoring.
        age_scoring_table : table with age scoring.
        building_type_column : name of buliding type column.
        roof_column : name of type of roof column.
        age_column :  name of age column.
        promotion_column : name of promotion column.
        score_column : name of score column.

    Returns:
        DataFrame with termo score.
    """
    dataframe = inventory.copy()

    require_columns(
        dataframe,
        [promotion_column, building_type_column, roof_column, age_column],
        context="apply_termo_scoring(inventory)",
    )

    if score_column not in dataframe.columns:
        raise KeyError(f"Missing column '{score_column}' required for scoring in inventory.")

    dataframe[promotion_column] = dataframe[promotion_column].astype(object)

    left = dataframe[[building_type_column, roof_column, age_column]].copy()

    if not roof_scoring_table.empty:
        roof_scoring_temp = roof_scoring_table.copy()
        first_column = roof_scoring_temp.columns[0]
        if first_column != roof_column:
            roof_scoring_temp = roof_scoring_temp.rename(columns={first_column: roof_column})
        left = left.merge(
            roof_scoring_temp,
            on=[building_type_column, roof_column],
            how="left",
            suffixes=("", "_roof"),
        )

    if not age_scoring_table.empty:
        age_scoring_temp = age_scoring_table.copy()
        first_column = age_scoring_temp.columns[0]
        if first_column != age_column:
            age_scoring_temp = age_scoring_temp.rename(columns={first_column: age_column})
        left = left.merge(
            age_scoring_temp,
            on=[building_type_column, age_column],
            how="left",
            suffixes=("", "_age"),
        )

    scoring_columns = [column for column in left.columns if str(column).startswith("Scoring")]
    if scoring_columns:
        dataframe["add_points"] = left[scoring_columns].sum(axis=1, skipna=False)
    else:
        dataframe["add_points"] = pd.NA

    score_numeric = pd.to_numeric(dataframe.get(score_column), errors="coerce")

    dataframe["final_points"] = np.where(
        dataframe[promotion_column] == "nie",
        score_numeric,
        np.floor(score_numeric + dataframe["add_points"]),
    )

    final_points_integer = pd.to_numeric(dataframe["final_points"], errors="coerce").astype("Int64")
    mapping = {1: "F", 2: "E", 3: "D", 4: "C", 5: "B", 6: "A"}
    dataframe["Klasa_termo"] = final_points_integer.map(mapping)

    return dataframe


def post_adjustments_and_join_demand(
    inventory: pd.DataFrame,
    demand: pd.DataFrame,
) -> pd.DataFrame:
    """
    Adjust Klasa_termo for newer buildings and join the demand table.
    Map 'skos' -> 'jednorodzinny' in Rodzaj_budynku.
    """
    if "Wiek_budynku_p_modern" in inventory.columns and "Klasa_termo" in inventory.columns:
        mask_new_2010 = (inventory["Wiek_budynku_p_modern"] == "Nowy po 2010r") & inventory["Klasa_termo"].isin(
            list("FED")
        )
        inventory.loc[mask_new_2010, "Klasa_termo"] = "C"

        mask_1990 = (inventory["Wiek_budynku_p_modern"] == "po 1990r.") & (inventory["Klasa_termo"] == "F")
        inventory.loc[mask_1990, "Klasa_termo"] = "E"

    if "Rodzaj_budynku" in inventory.columns:
        inventory.loc[inventory["Rodzaj_budynku"] == "skos", "Rodzaj_budynku"] = "jednorodzinny"

    required_columns = ["Rodzaj_budynku", "Klasa_termo"]
    if not set(required_columns).issubset(inventory.columns):
        logger.warning(
            "Cannot join demand (missing columns in inventory: %s).",
            [column for column in required_columns if column not in inventory.columns],
        )
        return inventory

    if demand.empty:
        logger.warning("Demand DataFrame is empty – skip join.")
        return inventory

    if not set(required_columns).issubset(demand.columns):
        logger.warning(
            "Cannot join demand (missing columns in demand: %s).",
            [column for column in required_columns if column not in demand.columns],
        )
        return inventory

    inventory = inventory.merge(demand, on=required_columns, how="left")
    return inventory


def attach_termo_flags(inventory: pd.DataFrame) -> pd.DataFrame:
    """
    Set klima/skosny flags and reclassify building type for 'skos' roofs.

    - klima = 'tak' if 'klim' in Uwagi (case-insensitive), otherwise 'nie'.
    - skosny = 'tak' if 'skos' in Uwagi (case-sensitive), otherwise 'nie'.
    - Rodzaj_budynku -> 'skos' when it was 'jednorodzinny' and skosny == 'tak'.
    """
    if "Uwagi" in inventory.columns:
        notes_series = inventory["Uwagi"].astype(str)
        has_air_conditioning = notes_series.str.contains("klim", case=False, na=False) & inventory["Uwagi"].notna()
        inventory["klima"] = np.where(has_air_conditioning, "tak", "nie")

        has_skos = notes_series.str.contains("skos", case=True, na=False) & inventory["Uwagi"].notna()
        inventory["skosny"] = np.where(has_skos, "tak", "nie")
    else:
        inventory["klima"] = "nie"
        inventory["skosny"] = "nie"

    if "Rodzaj_budynku" in inventory.columns:
        mask = (inventory["Rodzaj_budynku"] == "jednorodzinny") & (inventory["skosny"] == "tak")
        inventory.loc[mask, "Rodzaj_budynku"] = "skos"

    return inventory


def log_termo_summary(inventory: pd.DataFrame) -> None:
    """Count(Rodzaj_budynku, Klasa_termo) after mapping AB/EF."""
    needed_columns = {"Rodzaj_budynku", "Klasa_termo"}
    if not needed_columns.issubset(inventory.columns):
        logger.warning("Cannot logger termo summary — missing columns.")
        return
    temporary = inventory.copy()
    temporary["Klasa_termo"] = np.where(
        temporary["Klasa_termo"].isin(["E", "F"]),
        "EF",
        np.where(
            temporary["Klasa_termo"].isin(["A", "B"]),
            "AB",
            temporary["Klasa_termo"],
        ),
    )
    table = temporary.value_counts(["Rodzaj_budynku", "Klasa_termo"]).reset_index(name="n")
    logger.info(
        "Thermal class summary (bucketed AB/EF):\n%s",
        table.to_string(index=False),
    )


def log_missing_patterns(inventory: pd.DataFrame) -> None:
    """
    Log the number of rows with 0/1/2/3/4 missing values across the following columns:
    'Dach', 'Ocieplenie_ścian', 'Wiek_budynku_p_modern', 'Okna'.
    """
    columns = ["Dach", "Ocieplenie_ścian", "Wiek_budynku_p_modern", "Okna"]
    present = [column for column in columns if column in inventory.columns]
    if not present:
        logger.warning("Missingness logger skipped — none of %s present.", columns)
        return

    missing_matrix = inventory[present].isna()
    missing_counts_per_row = missing_matrix.sum(axis=1)
    counts = missing_counts_per_row.value_counts().sort_index()
    text = "\n".join(f"missing {i}: {int(counts.get(i, 0))}" for i in range(0, len(present) + 1))
    logger.info("Missingness (Dach/Ocieplenie/Wiek/Okna):\n%s", text)


def normalize_merged_id(series: pd.Series) -> pd.Series:
    """Normalize ID series to avoid join mismatches.
    - Standardize to regular strings (avoiding specific pandas StringDtype).
    - Remove trailing .0 from float IDs.
    - Strip whitespace.
    - Map 'nan', 'None' or empty to pd.NA.
    """
    # Convert to standard strings, handle float .0, strip whitespace
    s = series.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    # Map typical NaN string results to actual NA values
    s = s.replace({"nan": pd.NA, "None": pd.NA, "": pd.NA})
    return s


def normalize_col_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = pd.Index(df.columns).map(lambda c: str(c).replace("\u00a0", " ").strip())
    return df


def get_demand_data() -> pd.DataFrame:
    """
    Returns hardcoded demand data with building thermal characteristics.
    Columns: Rodzaj_budynku, Klasa_termo, heat, heat_water, cold
    Values use Polish number format (comma as decimal separator).
    """
    data = {
        "Rodzaj_budynku": [
            "jednorodzinny",
            "jednorodzinny",
            "jednorodzinny",
            "jednorodzinny",
            "jednorodzinny",
            "jednorodzinny",
            "wielorodzinny",
            "wielorodzinny",
            "wielorodzinny",
            "wielorodzinny",
            "wielorodzinny",
            "wielorodzinny",
            "kamienica",
            "kamienica",
            "kamienica",
            "kamienica",
            "kamienica",
            "kamienica",
            "inny",
            "inny",
            "inny",
            "inny",
            "inny",
            "inny",
            "biuro",
            "biuro",
            "biuro",
            "biuro",
            "biuro",
            "biuro",
            "handlowy",
            "handlowy",
            "handlowy",
            "handlowy",
            "handlowy",
            "handlowy",
        ],
        "Klasa_termo": [
            "F",
            "E",
            "D",
            "C",
            "B",
            "A",
            "F",
            "E",
            "D",
            "C",
            "B",
            "A",
            "F",
            "E",
            "D",
            "C",
            "B",
            "A",
            "F",
            "E",
            "D",
            "C",
            "B",
            "A",
            "F",
            "E",
            "D",
            "C",
            "B",
            "A",
            "F",
            "E",
            "D",
            "C",
            "B",
            "A",
        ],
        "heat": [
            251.04,
            196.1,
            119.43,
            74.58,
            47.16,
            31.7,
            230.97,
            164.45,
            131.65,
            80.2,
            56.24,
            30.11,
            246.46,
            193.32,
            118.29,
            69.3,
            55.47,
            40.02,
            202.94,
            188.67,
            148.22,
            83.77,
            56.92,
            37.42,
            228.13,
            175.57,
            121.05,
            84.73,
            54.47,
            36.31,
            222.2,
            150.87,
            137.38,
            70.61,
            51.35,
            37.99,
        ],
        "heat_water": [
            24.1,
            24.1,
            24.1,
            24.1,
            24.1,
            24.1,
            16.2,
            17.62,
            17.64,
            19.36,
            21.12,
            21.46,
            18.14,
            19.74,
            19.74,
            21.68,
            21.12,
            24.04,
            19.76,
            21.5,
            22.03,
            23.62,
            24.29,
            26.18,
            20.25,
            21.87,
            22.68,
            23.49,
            24.3,
            25.92,
            19.44,
            21.15,
            22.03,
            23.23,
            24.29,
            25.76,
        ],
        "cold": [
            18.25,
            20,
            22.8,
            28.51,
            33.17,
            34.1,
            27.66,
            27.66,
            27.66,
            27.66,
            27.66,
            27.66,
            27.73,
            27.73,
            27.73,
            27.73,
            27.73,
            27.73,
            5.73,
            5.73,
            5.73,
            5.73,
            6.59,
            5.73,
            4.98,
            4.98,
            4.98,
            4.98,
            4.98,
            4.98,
            7.56,
            7.56,
            7.56,
            7.56,
            8.69,
            7.56,
        ],
    }
    return pd.DataFrame(data)
