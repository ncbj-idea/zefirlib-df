from __future__ import annotations

import logging
from collections.abc import Iterable

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from datafusion.configs.postprocessing_config import PostprocessingConfig
from datafusion.constants import (
    COLUMN_CO_SOURCE,
    COLUMN_CWU_SOURCE,
    COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN,
    COLUMN_GAS_CONNECTED,
    COLUMN_H3_CONNECTIVITY,
    COLUMN_HEAT_CONNECTED,
    GROUPING_COLUMNS_OPERAT_A,
    GROUPING_COLUMNS_OPERAT_B,
    TABLE_HEAT_SOURCE_RESULT,
    TABLE_NON_MERGED_BDOT,
    TABLE_OPERAT_LOSOWANIA,
    VALUE_DISTRICT_HEATING,
    VALUE_GAS_BOILER,
)
from datafusion.postprocessing.helpers.helpers_creating_operat_losowania import (
    equal_or_nan_with_tolerance,
    print_summary_statistics,
)
from datafusion.utils.crud import load_dataframe_from_db, save_dataframe_to_db
from datafusion.utils.validation import require_columns

logger = logging.getLogger(__name__)

# ---------------------------
# Config & I/O
# ---------------------------


def read_inputs(engine: Engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read inputs for creating_operat_losowania from database.
    """

    revised_inventory = load_dataframe_from_db(engine, TABLE_HEAT_SOURCE_RESULT)
    non_merged_bdot = load_dataframe_from_db(engine, TABLE_NON_MERGED_BDOT)

    if revised_inventory.empty:
        raise ValueError("Read_to_operat is empty.")
    if non_merged_bdot.empty:
        logger.warning("Non merged bdot is empty.")

    return (
        revised_inventory,
        non_merged_bdot,
    )


def normalize_string(dataframe: pd.DataFrame, columns: Iterable[str], lowercase: bool = False) -> None:
    """Normalize text columns by stripping whitespace and optionally converting
    to lowercase."""
    for column in columns:
        if column in dataframe.columns:
            series = dataframe[column].astype(str).str.strip()
            dataframe[column] = series.str.lower() if lowercase else series
        else:
            logger.warning(
                "normalize_string: column %s not present – skipping normalization.",
                column,
            )


# ---------------------------
# Core of logic
# ---------------------------


def apply_connectivity_flags(dataframe: pd.DataFrame) -> None:
    if dataframe.empty:
        logger.warning("apply_connectivity_flags: dataframe is empty – nothing to do.")
        return

    require_columns(
        dataframe,
        [COLUMN_CO_SOURCE, COLUMN_CWU_SOURCE],
        context="apply_connectivity_flags",
    )

    dataframe[COLUMN_HEAT_CONNECTED] = False
    dataframe[COLUMN_GAS_CONNECTED] = False
    dataframe[COLUMN_H3_CONNECTIVITY] = False

    heat_mask = dataframe[COLUMN_CO_SOURCE].notna() & (
        (dataframe[COLUMN_CO_SOURCE] == VALUE_DISTRICT_HEATING)
        | (dataframe[COLUMN_CWU_SOURCE] == VALUE_DISTRICT_HEATING)
    )
    dataframe.loc[heat_mask, [COLUMN_HEAT_CONNECTED, COLUMN_H3_CONNECTIVITY]] = True

    gas_mask = dataframe[COLUMN_CO_SOURCE].notna() & (
        (dataframe[COLUMN_CO_SOURCE] == VALUE_GAS_BOILER) | (dataframe[COLUMN_CWU_SOURCE] == VALUE_GAS_BOILER)
    )
    dataframe.loc[gas_mask, COLUMN_GAS_CONNECTED] = True


def make_a_subset_with_optional_solar_swap(
    revised_inventory: pd.DataFrame,
    solar_enabled: bool,
    solar_centralne_value: str,
    solar_cwu_value: str,
    solar_replacement_value: str,
) -> pd.DataFrame:
    """
    First, filter for A & != Public buildings.
    Only then replace “Solar collectors” → “Electric heating” WITHIN THIS SUBSET.
    """
    if revised_inventory.empty:
        logger.warning("make_a_subset_with_optional_solar_swap: input is empty.")
        return revised_inventory.copy()

    require_columns(
        revised_inventory,
        ["typ_deklaracji", COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN, COLUMN_CO_SOURCE, COLUMN_CWU_SOURCE],
        context="make_a_subset_with_optional_solar_swap",
    )

    subset_a = revised_inventory[
        (revised_inventory["typ_deklaracji"] == "A")
        & (revised_inventory[COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN] != "Budynki publiczne")
    ].copy()

    if subset_a.empty:
        logger.warning("make_a_subset_with_optional_solar_swap: subset A is empty after filters.")
        return subset_a

    if solar_enabled:
        subset_a.loc[subset_a[COLUMN_CO_SOURCE] == solar_centralne_value, COLUMN_CO_SOURCE] = solar_replacement_value
        subset_a.loc[subset_a[COLUMN_CWU_SOURCE] == solar_cwu_value, COLUMN_CWU_SOURCE] = solar_replacement_value

    return subset_a


def build_operat_a(operat_a_with_trash_input: pd.DataFrame, ratio_threshold_a: float) -> pd.DataFrame:
    """
    Remove trash zones in A according to share threshold (ratio_threshold_a).
    Logs number of zones and hot water replacements.

    Args:
        operat_a_with_trash_input : input operat A with weights and grouping vars.
        ratio_threshold_a : maximum share threshold for marking groups as trash.

    Returns:
        cleaned operat A with updated CWU assignments and 'losowania' flag.

    """
    if operat_a_with_trash_input.empty:
        logger.warning("build_operat_a: input is empty – returning empty operat_a.")
        return operat_a_with_trash_input.copy().assign(losowania="A")

    require_columns(
        operat_a_with_trash_input,
        [*GROUPING_COLUMNS_OPERAT_A, "weight"],
        context="build_operat_a",
    )

    operat_a = operat_a_with_trash_input.copy()

    trash_groups = (
        operat_a.groupby(
            GROUPING_COLUMNS_OPERAT_A,
            dropna=False,
        )["weight"]
        .sum()
        .reset_index(name="suma_wag")
    )

    for col in GROUPING_COLUMNS_OPERAT_A:
        if col in operat_a.columns and trash_groups[col].dtype != operat_a[col].dtype:
            trash_groups[col] = trash_groups[col].astype(operat_a[col].dtype)

    total_weight = trash_groups["suma_wag"].sum()
    if total_weight == 0 or pd.isna(total_weight):
        logger.warning("A: sum of weights in groups = 0/NaN – I am disregarding hot water exchanges.")
        selected_trash_groups = trash_groups.iloc[0:0].copy()
    else:
        selected_trash_groups = (
            trash_groups.assign(prop=lambda dataframe: dataframe["suma_wag"] / total_weight)
            .query("prop <= @ratio_threshold_a")
            .assign(new_cwu=lambda dataframe: dataframe[COLUMN_CO_SOURCE])
        )

    number_of_trash_groups = len(selected_trash_groups)

    affected_rows = (
        operat_a.merge(
            selected_trash_groups[GROUPING_COLUMNS_OPERAT_A],
            on=GROUPING_COLUMNS_OPERAT_A,
            how="inner",
        ).shape[0]
        if number_of_trash_groups > 0
        else 0
    )
    logger.info(
        "A: number of garbage zones with cwu→central replacement: %d (records affected: %d)",
        number_of_trash_groups,
        affected_rows,
    )

    if number_of_trash_groups > 0:
        operat_a = operat_a.merge(
            selected_trash_groups[[*GROUPING_COLUMNS_OPERAT_A, "new_cwu"]],
            on=GROUPING_COLUMNS_OPERAT_A,
            how="left",
        )
        operat_a[COLUMN_CWU_SOURCE] = np.where(
            operat_a["new_cwu"].notna(), operat_a["new_cwu"], operat_a[COLUMN_CWU_SOURCE]
        )
        operat_a = operat_a.drop(columns=["new_cwu"], errors="ignore")

    return operat_a.assign(losowania="A")


def build_operat_b(
    revised_inventory: pd.DataFrame,
    tourism_functions: set[str],
    threshold_b_ratio: float,
    float_tolerance: float,
) -> pd.DataFrame:
    """
    Build operat B from revised inventory, with special handling of declaration types,
    usable area adjustments, and removal of low-share (“trash”) hot water groups.

    Args:
        revised_inventory : input CEEB-like inventory.
        tourism_functions : functions treated as tourism for A→B extraction.
        threshold_b_ratio : max share threshold for marking groups as trash.
        float_tolerance : tolerance for comparing areas.

    Returns:
        constructed operat B with 'losowania' flag.
    """
    if revised_inventory.empty:
        logger.warning("build_operat_B: revised_inventory is empty – returning empty B.")
        return revised_inventory.copy()

    require_columns(
        revised_inventory,
        [
            "merged_id",
            "typ_deklaracji",
            "pow_obrysu_m2",
            "pow_uzytkowa_m2",
            COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN,
            "funkcja_szczegolowa_budynku",
            "id",
            COLUMN_CO_SOURCE,
            COLUMN_CWU_SOURCE,
            COLUMN_H3_CONNECTIVITY,
        ],
        context="build_operat_b",
    )

    ceeb = revised_inventory.copy()

    declaration_type_sets = ceeb.groupby("merged_id")["typ_deklaracji"].agg(lambda series: set(series))
    only_b_ids = [merged_id for merged_id, declaration_set in declaration_type_sets.items() if declaration_set == {"B"}]
    first_part = ceeb[ceeb["merged_id"].isin(only_b_ids)].copy()

    residential_mask = first_part[COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN].eq(
        "Budynki o dwóch mieszkaniach i wielomieszkaniowe"
    )
    equal_mask = equal_or_nan_with_tolerance(
        first_part["pow_obrysu_m2"], first_part["pow_uzytkowa_m2"], float_tolerance
    )
    first_part.loc[residential_mask & equal_mask, "pow_uzytkowa_m2"] = (
        first_part.loc[residential_mask & equal_mask, "pow_obrysu_m2"] * 0.5
    )
    first_part.loc[residential_mask & (~equal_mask), "pow_uzytkowa_m2"] = first_part.loc[
        residential_mask & (~equal_mask), "pow_obrysu_m2"
    ]

    second_part = ceeb[
        (ceeb["funkcja_szczegolowa_budynku"].isin(tourism_functions)) & (ceeb["typ_deklaracji"] == "A")
    ].copy()

    group_types = (
        ceeb.groupby("merged_id")
        .agg(
            number_of_declaration_types=(
                "typ_deklaracji",
                lambda series: len(set(series)),
            ),
            category=(
                COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN,
                lambda series: series.iloc[0],
            ),
        )
        .reset_index()
    )

    third_ids = group_types[
        (group_types["number_of_declaration_types"] == 2) & (group_types["category"] != "Budynki publiczne")
    ]["merged_id"].tolist()
    third_part = ceeb[(ceeb["merged_id"].isin(third_ids)) & (ceeb["typ_deklaracji"] == "B")].copy()
    equal_mask_third = equal_or_nan_with_tolerance(
        third_part["pow_obrysu_m2"], third_part["pow_uzytkowa_m2"], float_tolerance
    )
    third_part.loc[equal_mask_third, "pow_uzytkowa_m2"] = third_part.loc[equal_mask_third, "pow_obrysu_m2"] * 0.5
    third_part.loc[~equal_mask_third, "pow_uzytkowa_m2"] = third_part.loc[~equal_mask_third, "pow_obrysu_m2"]

    fourth_ids = group_types[
        (group_types["number_of_declaration_types"] == 2) & (group_types["category"] == "Budynki publiczne")
    ]["merged_id"].tolist()
    fourth_part = ceeb[(ceeb["merged_id"].isin(fourth_ids)) & (ceeb["typ_deklaracji"] == "B")].copy()

    excluded_ids = set(fourth_part["id"].tolist())
    operat_b = pd.concat(
        [
            first_part[~first_part["id"].isin(excluded_ids)],
            second_part[~second_part["id"].isin(excluded_ids)],
            third_part,
            fourth_part,
        ],
        ignore_index=True,
    )

    if operat_b.empty:
        logger.warning("build_operat_b: operat_b empty after combining parts.")
        return operat_b.assign(losowania="B")

    counts = (
        operat_b.groupby([COLUMN_CO_SOURCE, COLUMN_CWU_SOURCE, COLUMN_H3_CONNECTIVITY], dropna=False)
        .size()
        .reset_index(name="n")
    )
    total_count = counts["n"].sum()
    if total_count == 0 or pd.isna(total_count):
        logger.warning("B: sum of group sizes = 0/NaN – I ignore hot water exchanges.")
        trash_b = counts.iloc[0:0].copy()
    else:
        trash_b = (
            counts.assign(prop=lambda dataframe: dataframe["n"] / total_count)
            .query("prop <= @threshold_b_ratio")
            .assign(new_cwu=lambda dataframe: dataframe[COLUMN_CO_SOURCE])
        )

    number_of_trash_groups = len(trash_b)
    affected_rows = (
        operat_b.merge(
            trash_b[GROUPING_COLUMNS_OPERAT_B],
            on=GROUPING_COLUMNS_OPERAT_B,
            how="inner",
        ).shape[0]
        if number_of_trash_groups > 0
        else 0
    )
    logger.info(
        "B: number of garbage zones with hot water replacement → central: %d (records affected: %d)",
        number_of_trash_groups,
        affected_rows,
    )

    if number_of_trash_groups > 0:
        operat_b = operat_b.merge(
            trash_b[
                [
                    *GROUPING_COLUMNS_OPERAT_B,
                    "new_cwu",
                ]
            ],
            on=GROUPING_COLUMNS_OPERAT_B,
            how="left",
        )
        operat_b[COLUMN_CWU_SOURCE] = np.where(
            operat_b["new_cwu"].notna(), operat_b["new_cwu"], operat_b[COLUMN_CWU_SOURCE]
        )
        operat_b = operat_b.drop(columns=["new_cwu"], errors="ignore")

    return operat_b.assign(losowania="B")


def assign_building_kind(
    operat: pd.DataFrame,
    operat_a: pd.DataFrame,
    operat_b: pd.DataFrame,
    by_general: dict[str, set[str]],
    by_specific: dict[str, set[str]],
) -> pd.DataFrame:
    """
    Like 'rodzaj_row':
        first, the general mapping → sets the type
        then, the specific mapping only where it’s still “inny”
        then, the x_diff rule for B
    """
    if operat.empty:
        logger.warning("assign_building_kind: operat is empty – nothing to assign.")
        return operat

    require_columns(
        operat,
        [
            "nazwa_funkcji_ogolnej",
            "funkcja_szczegolowa_budynku",
            "losowania",
            "merged_id",
            COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN,
        ],
        context="assign_building_kind – operat",
    )
    require_columns(
        operat_a,
        ["merged_id", COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN],
        context="assign_building_kind – operat_a",
    )
    require_columns(
        operat_b,
        ["merged_id", COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN],
        context="assign_building_kind – operat_b",
    )

    building_kind_series = pd.Series("inny", index=operat.index)
    general_function = operat["nazwa_funkcji_ogolnej"]
    specific_function = operat["funkcja_szczegolowa_budynku"]

    for label, values in by_general.items():
        building_kind_series = building_kind_series.mask(general_function.isin(values), label)

    for label, values in by_specific.items():
        mask_new = (building_kind_series == "inny") & specific_function.isin(values)
        building_kind_series = building_kind_series.mask(mask_new, label)

    operat = operat.copy()
    operat["Rodzaj_budynku"] = building_kind_series

    non_public_id_list_b = operat_b.loc[
        operat_b[COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN] != "Budynki publiczne", "merged_id"
    ]
    non_public_id_list_a = operat_a.loc[
        operat_a[COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN] != "Budynki publiczne", "merged_id"
    ]
    x_diff = set(pd.unique(non_public_id_list_b)) - set(pd.unique(non_public_id_list_a))

    mask_b_in_diff = (operat["losowania"] == "B") & (operat["merged_id"].isin(x_diff))
    operat.loc[mask_b_in_diff, "Rodzaj_budynku"] = "inny"

    return operat


def apply_kamienica_rules(
    dataframe: pd.DataFrame,
    enabled: bool,
    monument_column: str,
    kamienica_column: str,
    apply_over: set[str],
) -> None:
    """Apply tenement house rules if enabled in config."""
    if not enabled:
        return
    if dataframe.empty:
        logger.warning("apply_kamienica_rules: dataframe is empty – nothing to do.")
        return
    require_columns(
        dataframe,
        ["Rodzaj_budynku"],
        context="apply_kamienica_rules",
    )

    if monument_column in dataframe.columns:
        monument_mask = dataframe["Rodzaj_budynku"].isin(apply_over) & (dataframe[monument_column] == 1)
        dataframe.loc[monument_mask, "Rodzaj_budynku"] = "kamienica"
    if kamienica_column in dataframe.columns:
        kamienica_normalized = dataframe[kamienica_column].astype(str).str.strip().str.lower()
        kamienica_mask = dataframe["Rodzaj_budynku"].isin(apply_over) & (kamienica_normalized == "tak")
        dataframe.loc[kamienica_mask, "Rodzaj_budynku"] = "kamienica"


# ---------------------------
# Orchestration
# ---------------------------


def run_creating_operat_losowania(
    engine: Engine,
    config: PostprocessingConfig,
) -> None:
    """
    Build sampling operat (A + B + non-merged BDOT), apply rules, and save to Excel.

    Args:
        config : PostprocessingConfig instance.
    """
    thresholds = config.thresholds

    revised_inventory, non_merged_bdot = read_inputs(engine)

    normalization_config = config.normalize
    normalize_string(
        revised_inventory,
        normalization_config.columns,
        lowercase=normalization_config.lowercase,
    )

    apply_connectivity_flags(revised_inventory)

    if config.print_summaries.enabled:
        print_summary_statistics(revised_inventory)

    solar_config = config.solar_to_electric
    subset_a = make_a_subset_with_optional_solar_swap(
        revised_inventory=revised_inventory,
        solar_enabled=solar_config.enabled,
        solar_centralne_value=solar_config.centralne_value,
        solar_cwu_value=solar_config.cwu_value,
        solar_replacement_value=solar_config.replacement,
    )

    operat_losowania_a = build_operat_a(
        subset_a,
        ratio_threshold_a=thresholds.threshold_a_ratio,
    )

    operat_losowania_b = build_operat_b(
        revised_inventory=revised_inventory,
        tourism_functions=set(config.tourism_functions),
        threshold_b_ratio=thresholds.threshold_b_ratio,
        float_tolerance=thresholds.float_tol,
    )

    operat_losowania = pd.concat(
        [operat_losowania_a, operat_losowania_b],
        ignore_index=True,
    )

    non_merged_bdot = non_merged_bdot.copy()
    if not non_merged_bdot.empty:
        non_merged_bdot["losowania"] = "brak"
        operat_losowania = pd.concat([operat_losowania, non_merged_bdot], ignore_index=True)
    else:
        logger.warning("run_creating_operat_losowania: non_merged_bdot is empty.")

    building_kind_config = config.building_kind
    by_general = {key: set(value) for key, value in building_kind_config.by_general.model_dump().items()}
    by_specific = {key: set(value) for key, value in building_kind_config.by_specific.model_dump().items()}
    operat_losowania = assign_building_kind(
        operat=operat_losowania,
        operat_a=operat_losowania_a,
        operat_b=operat_losowania_b,
        by_general=by_general,
        by_specific=by_specific,
    )

    kamienica_config = config.kamienica_rules
    apply_kamienica_rules(
        operat_losowania,
        enabled=kamienica_config.enabled,
        monument_column=kamienica_config.monument_col,
        kamienica_column=kamienica_config.kamienica_col,
        apply_over=set(kamienica_config.apply_over),
    )

    save_dataframe_to_db(engine, operat_losowania, TABLE_OPERAT_LOSOWANIA)
    logger.info("Saved operat_losowania to database.")
    logger.info("Ended part Creating_operat_losowania.")
