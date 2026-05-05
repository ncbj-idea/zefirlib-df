from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

from datafusion.configs.postprocessing_config import PostprocessingConfig
from datafusion.postprocessing.helpers.helpers_estimations import _ensure_directory
from datafusion.postprocessing.helpers.save_to_konfigurator import save_to_konfigurator
from datafusion.utils.crud import load_dataframe_from_db, save_dataframe_to_db
from datafusion.utils.validation import require_columns

logger = logging.getLogger(__name__)


# ---------------------------
# Constants
# ---------------------------

REQUIRED_COLUMNS = [
    "Rodzaj_budynku",
    "powierzchnia",
    "yearly_heat_demand",
    "yearly_heat_water_demand",
    "Ogrzewanie_elektryczne",
    "cwu_Ogrzewanie_elektryczne",
    "Pompa_ciepła",
    "cwu_Pompa_ciepła",
]

SHARE_COLUMNS = [
    "Ogrzewanie_elektryczne",
    "cwu_Ogrzewanie_elektryczne",
    "Pompa_ciepła",
    "cwu_Pompa_ciepła",
]

NUMERIC_COLUMNS = SHARE_COLUMNS + [
    "yearly_heat_demand",
    "yearly_heat_water_demand",
    "powierzchnia",
]

BUILDING_TYPES_RESIDENTIAL = ["jednorodzinny", "wielorodzinny"]
BUILDING_TYPES_NON_RESIDENTIAL = ["biuro", "handlowy", "inny"]

# ---------------------------
# Logic of EE division for residential buildings
# ---------------------------


def divide_living_energy(
    total_electricity: float,
    multi_family_area: float,
    single_family_area: float,
    multi_family_factor: float,
) -> dict[str, float]:
    """
    Divide total electricity consumption between multi-family and single-family buildings.

    Args:
        total_electricity: Total electricity consumption in kWh.
        multi_family_area: Total area of multi-family buildings in m².
        single_family_area: Total area of single-family buildings in m².
        multi_family_factor: Factor for multi-family electricity intensity.

    Returns:
        Dictionary with keys:
        - ee_multi: kWh/m² for multi-family buildings
        - ee_single: kWh/m² for single-family buildings

    Raises:
        ValueError: If areas are invalid or sum to zero.
    """
    if total_electricity < 0:
        logger.warning(
            "divide_living_energy: total_electricity < 0 (%.3f) – to wygląda podejrzanie.",
            total_electricity,
        )

    total_area = multi_family_area + single_family_area
    if total_area <= 0:
        raise ValueError(
            f"Sum of areas must be > 0. Got multi_family_area={multi_family_area}, "
            f"single_family_area={single_family_area}."
        )

    electricity_per_square_meter = total_electricity / total_area

    if multi_family_factor < 0:
        logger.warning(
            "divide_living_energy: multi_family_factor < 0 (%.3f) – używam, ale to jest nielogiczne.",
            multi_family_factor,
        )

    electricity_multi_family = electricity_per_square_meter * multi_family_factor
    # Total electricity for multi-family buildings
    electricity_multi_family_total = electricity_multi_family * multi_family_area
    # Remaining electricity for single-family buildings
    electricity_single_family_total = total_electricity - electricity_multi_family_total
    # Per m² for single-family buildings
    electricity_single_family = electricity_single_family_total / single_family_area if single_family_area > 0 else 0.0

    # Validate outputs are non-negative
    if electricity_multi_family < 0:
        logger.warning(
            "divide_living_energy: calculated ee_multi (%.3f) is negative - setting to 0.0",
            electricity_multi_family,
        )
        electricity_multi_family = 0.0
    if electricity_single_family < 0:
        logger.warning(
            "divide_living_energy: calculated ee_single (%.3f) is negative - setting to 0.0",
            electricity_single_family,
        )
        electricity_single_family = 0.0

    return {
        "ee_multi": electricity_multi_family,
        "ee_single": electricity_single_family,
    }


# ---------------------------
# Protostrefy
# ---------------------------


def run_protostrefy(
    base_directory: Path,
    engine: Engine,
    config: PostprocessingConfig,
) -> pd.DataFrame:
    """
    Process protostrefy zones and generate electricity demand calculations.

    Args:
        base_directory: Base directory for output files (strefy/protostrefy.xlsx).
        engine: SQLAlchemy database engine for loading protostrefy_a and protostrefy_b tables.
        config: PostprocessingConfig instance containing electricity parameters and column mappings.

    Returns:
        DataFrame with combined zones A and B, renamed columns, and calculated electricity demand.

    Raises:
        RuntimeError: If required configuration parameters are missing.
        ValueError: If input data is empty or invalid.
        KeyError: If required columns are missing from input data.
    """

    base_path = Path(base_directory).expanduser().resolve()

    params_config = config.params
    protozones_config = config.protostrefy

    try:
        heat_pump_efficiency = float(params_config.heat_pump)
        electric_heater_efficiency = float(params_config.electric_heater)
    except (KeyError, AttributeError) as exc:
        raise RuntimeError(
            f"Parameter missing {exc.args[0] if exc.args else 'unknown'} in the 'params' section of the config."
        ) from exc

    if heat_pump_efficiency <= 0 or electric_heater_efficiency <= 0:
        raise ValueError(
            f"Efficiencies must be > 0. Got heat_pump={heat_pump_efficiency}, "
            f"electric_heater={electric_heater_efficiency}."
        )

    expected_columns = protozones_config.expected_cols
    new_columns = protozones_config.new_cols

    if not expected_columns or not new_columns:
        raise RuntimeError("The protostrefy.expected_cols or protostrefy.new_cols section is missing in the config.")
    if not isinstance(expected_columns, (list, tuple)) or not isinstance(new_columns, (list, tuple)):
        raise TypeError("protostrefy.expected_cols and protostrefy.new_cols must be lists in config.")

    output_path = base_path / "strefy" / "protostrefy.xlsx"

    living_electricity_config = protozones_config.ee_living
    try:
        total_living_electricity = float(living_electricity_config.ee_total)
        multi_family_living_area = float(living_electricity_config.multi_area)
        single_family_living_area = float(living_electricity_config.single_area)
        multi_family_factor = float(living_electricity_config.ee_factor or 1.0)
    except (KeyError, AttributeError) as exc:
        raise RuntimeError(
            f"Parameter missing {exc.args[0] if exc.args else 'unknown'} in protostrefy.ee_living in config"
        ) from exc

    living_electricity = divide_living_energy(
        total_electricity=total_living_electricity,
        multi_family_area=multi_family_living_area,
        single_family_area=single_family_living_area,
        multi_family_factor=multi_family_factor,
    )
    ee_single_family = living_electricity["ee_single"]
    ee_multi_family = living_electricity["ee_multi"]

    electricity_intensity_config = protozones_config.ee_intensity
    electricity_other = electricity_intensity_config.inny
    electricity_office = electricity_intensity_config.biuro
    electricity_commercial = electricity_intensity_config.handlowy
    electricity_monument = electricity_intensity_config.zabytek
    electricity_tenement = electricity_intensity_config.kamienica

    zones_a = load_dataframe_from_db(engine, "protostrefy_a")
    zones_b = load_dataframe_from_db(engine, "protostrefy_b")

    logger.debug("Loaded columns: %s", zones_a.columns.to_list())

    require_columns(zones_a, REQUIRED_COLUMNS, context="zones_a")
    require_columns(zones_b, REQUIRED_COLUMNS, context="zones_b")

    try:
        logger.info(
            "Total area A by building type:\n%s",
            zones_a.groupby("Rodzaj_budynku", dropna=False)["powierzchnia"].sum().to_string(),
        )
        logger.info(
            "Total area B by building type:\n%s",
            zones_b.groupby("Rodzaj_budynku", dropna=False)["powierzchnia"].sum().to_string(),
        )
    except Exception as e:
        logger.warning("Could not calculate area sums: %s", e)

    # Convert numeric columns efficiently
    for col in NUMERIC_COLUMNS:
        zones_a[col] = pd.to_numeric(zones_a[col], errors="coerce").fillna(0.0)

    zones_a["ee_heat_demand"] = (
        zones_a["yearly_heat_demand"] * zones_a["Ogrzewanie_elektryczne"] / electric_heater_efficiency
        + zones_a["yearly_heat_water_demand"] * zones_a["cwu_Ogrzewanie_elektryczne"] / electric_heater_efficiency
        + zones_a["yearly_heat_demand"] * zones_a["Pompa_ciepła"] / heat_pump_efficiency
        + zones_a["yearly_heat_water_demand"] * zones_a["cwu_Pompa_ciepła"] / heat_pump_efficiency
    )

    # Vectorized electricity demand calculation for residential buildings
    building_type_factors = {
        "jednorodzinny": ee_single_family,
        "wielorodzinny": ee_multi_family,
    }
    zones_a["ee_demand"] = (
        zones_a["Rodzaj_budynku"].map(building_type_factors).fillna(electricity_tenement) * zones_a["powierzchnia"]
    )

    # Convert numeric columns efficiently
    for col in NUMERIC_COLUMNS:
        zones_b[col] = pd.to_numeric(zones_b[col], errors="coerce").fillna(0.0)

    zones_b["ee_heat_demand"] = (
        zones_b["yearly_heat_demand"] * zones_b["Ogrzewanie_elektryczne"] / electric_heater_efficiency
        + zones_b["yearly_heat_water_demand"] * zones_b["cwu_Ogrzewanie_elektryczne"] / electric_heater_efficiency
        + zones_b["yearly_heat_demand"] * zones_b["Pompa_ciepła"] / heat_pump_efficiency
        + zones_b["yearly_heat_water_demand"] * zones_b["cwu_Pompa_ciepła"] / heat_pump_efficiency
    )

    # Vectorized electricity demand calculation for non-residential buildings
    building_type_factors_b = {
        "biuro": electricity_office,
        "handlowy": electricity_commercial,
        "inny": electricity_other,
    }
    zones_b["ee_demand"] = (
        zones_b["Rodzaj_budynku"].map(building_type_factors_b).fillna(electricity_monument) * zones_b["powierzchnia"]
    )

    combined_zones = pd.concat([zones_b, zones_a], ignore_index=True)

    if combined_zones.empty:
        raise ValueError("Combined protozones (A+B) are empty after concatenation.")

    if "strata" in combined_zones.columns:
        combined_zones = combined_zones.drop(columns=["strata"])

    # Use set operations for efficient column checking
    missing_columns = set(expected_columns) - set(combined_zones.columns)
    if missing_columns:
        raise KeyError(
            "Missing columns in protozones before rename (from YAML protostrefy.expected_cols): "
            f"{missing_columns}. Present columns: {list(combined_zones.columns)}"
        )

    combined_zones = combined_zones[list(expected_columns)]

    if len(expected_columns) != len(new_columns):
        raise ValueError(
            f"Number of expected_cols ({len(expected_columns)}) != number of new_cols ({len(new_columns)})."
        )

    combined_zones.columns = list(new_columns)
    save_dataframe_to_db(engine, combined_zones, "protostrefy")

    _ensure_directory(output_path)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        combined_zones.to_excel(writer, index=False, sheet_name="protostrefy")

    logger.info("protostrefy: saved in %s", output_path)

    # Save to konfigurator Excel file
    save_to_konfigurator(combined_zones, output_path=base_path)

    return combined_zones
