from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from datafusion.configs.postprocessing_config import PostprocessingConfig
from datafusion.constants import COLUMN_BUILDING_TYPE, TABLE_OPERAT_LOSOWANIA, TABLE_PROCESSED_BDOT
from datafusion.utils.crud import load_dataframe_from_db
from datafusion.utils.validation import require_columns

_logger = logging.getLogger(__name__)

GLOBAL_VALUES_FILENAME = "global_values.csv"

# ---------------------------
# Inputs
# ---------------------------


def read_global_inputs(
    engine: Engine,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read inputs from database.
    """

    bdot_frame = load_dataframe_from_db(engine, TABLE_PROCESSED_BDOT)
    sampling_frame = load_dataframe_from_db(engine, TABLE_OPERAT_LOSOWANIA)

    if bdot_frame.empty:
        raise ValueError("Delicious bdot is empty.")
    if sampling_frame.empty:
        _logger.warning("Heat source result is empty.")

    return bdot_frame, sampling_frame


# ---------------------------
# Helpers
# ---------------------------


def distinct_by_key(dataframe: pd.DataFrame, key: str) -> pd.DataFrame:
    if dataframe.empty:
        _logger.warning("distinct_by_key: dataframe is empty – returning empty frame.")
        return dataframe.copy()
    if key not in dataframe.columns:
        raise KeyError(f"distinct_by_key: missing column '{key}'. Present: {list(dataframe.columns)}")
    return dataframe[~dataframe[key].duplicated(keep="first")].copy()


def validate_taxonomy(config: dict | None) -> None:
    """
    Validate taxonomy section in config, checking for duplicated or conflicting
    categorical mappings across taxonomy subsections.

    Args:
        config : configuration dictionary possibly containing a taxonomy.

    Returns:
        valueerror if conflicting mappings are detected.
    """
    if not isinstance(config, dict):
        return
    taxonomy = config.get("taxonomy", config)
    if not isinstance(taxonomy, dict):
        return

    seen: dict[str, tuple[str, str]] = {}
    conflicts: list[tuple[Any, tuple[str, str], tuple[str, str]]] = []
    for section in ("mieszkalne", "by_specific"):
        section_dict = taxonomy.get(section, {})
        if not isinstance(section_dict, dict):
            continue
        for kind, values in section_dict.items():
            for value in values or []:
                key = str(value).strip().lower()
                if key in seen and seen[key] != (section, kind):
                    conflicts.append((value, seen[key], (section, kind)))
                else:
                    seen[key] = (section, kind)
    if conflicts:
        raise ValueError(f"Conflicting mapping in taxonomy: {conflicts[:5]} ...")


def assign_building_kind_from_specific(dataframe: pd.DataFrame, config: dict | None = None) -> pd.Series:
    """
    Assign 'Rodzaj_budynku' from 'funkcja_szczegolowa_budynku' as in config.yaml:
      taxonomy.mieszkalne:
         wielorodzinny: [ ... ]
         jednorodzinny: [ ... ]
      taxonomy.by_specific:
         handlowy: [ ... ]
         biuro: [ ... ]
         przemysł: [ ... ]
         ...
    Priority: first residential, then by_specific, and by default "inny".
    """
    if dataframe.empty:
        _logger.warning("assign_building_kind_from_specific: dataframe is empty – returning empty Series.")
        return pd.Series([], dtype="object")

    require_columns(
        dataframe,
        ["funkcja_szczegolowa_budynku"],
        context="assign_building_kind_from_specific",
    )

    config = config or {}
    validate_taxonomy(config)

    specific_function = dataframe["funkcja_szczegolowa_budynku"].astype(str)

    default_config = {
        "mieszkalne": {
            "wielorodzinny": ["budynek wielorodzinny", "budynek o dwóch mieszkaniach"],
            "jednorodzinny": ["budynek jednorodzinny"],
        },
        "by_specific": {
            "handlowy": [
                "centrum handlowe",
                "pawilon handlowo-usługowy",
                "apteka",
                "hala targowa -  do sprawdzenia",
                "hipermarket lub supermarket",
                "dom towarowy lub handlowy",
            ],
            "biuro": [
                "siedziba firmy lub firm",
                "inny urząd administracji publicznej",
                "bank",
                "sąd",
                "prokuratura",
            ],
            "przemysł": ["produkcyjny"],
            "nie_ujęte": [
                "szklarnia lub cieplarnia",
                "garaż",
                "budynek gospodarczy",
                "toaleta publiczna",
                "stacja transformatorowa",
                "hala wystawowa",
                "budynek produkcyjny zwierząt hodowlanych",
                "korty tenisowe",
                "halowy tor gokartowy",
                "ujeżdżalnia",
                "pływalnia",
                "hala sportowa",
                "hala widowiskowa",
                "stacja transformatorowa",
                "elewator",
            ],
        },
    }

    taxonomy = (config or {}).get("taxonomy", {})
    residential_config = taxonomy.get("mieszkalne", default_config["mieszkalne"])
    by_specific_config = taxonomy.get("by_specific", default_config["by_specific"])

    building_type = pd.Series("inny", index=dataframe.index, dtype="object")

    for kind, values in residential_config.items():
        building_type[specific_function.isin(set(values))] = kind

    for kind, values in by_specific_config.items():
        building_type[specific_function.isin(set(values))] = kind

    return building_type


def boolean_to_label(series: pd.Series, label_true: str, label_false: str) -> pd.Series:
    series_copy = series.copy()
    result = pd.Series(pd.NA, index=series_copy.index, dtype="object")
    result[series_copy] = label_true
    result[not series_copy] = label_false
    return result


# ---------------------------
# Core steps (BDOT / OPERAT)
# ---------------------------


def prepare_bdot_frame(bdot_frame: pd.DataFrame, gus_factor: float) -> pd.DataFrame:
    """
    - distinct by merged_id
    - assign Rodzaj_budynku from szczegółowa funkcja
    - drop ['nie_ujęte', 'przemysł']
    - compute latent_area:
        pow_uzytkowa_m2 * wsp... * (gus_factor for mieszkalne)
    """
    if bdot_frame.empty:
        _logger.warning("prepare_bdot_frame: input BDOT is empty – returning empty.")
        return bdot_frame.copy()

    require_columns(
        bdot_frame,
        [
            "merged_id",
            "funkcja_szczegolowa_budynku",
            "pow_uzytkowa_m2",
            "wspolczynnik_powierzchni_uzytkowej_do_powierzchni_zabudowy",
        ],
        context="prepare_bdot_frame",
    )

    bdot_frame = distinct_by_key(bdot_frame, "merged_id")
    bdot_frame[COLUMN_BUILDING_TYPE] = assign_building_kind_from_specific(bdot_frame)
    bdot_frame = bdot_frame[~bdot_frame[COLUMN_BUILDING_TYPE].isin(["nie_ujęte", "przemysł"])].copy()

    if bdot_frame.empty:
        _logger.warning("prepare_bdot_frame: all rows filtered out after Rodzaj_budynku filter.")
        return bdot_frame

    residential_mask = bdot_frame[COLUMN_BUILDING_TYPE].isin(["wielorodzinny", "jednorodzinny"])
    bdot_frame["latent_area"] = (
        bdot_frame["pow_uzytkowa_m2"]
        * bdot_frame["wspolczynnik_powierzchni_uzytkowej_do_powierzchni_zabudowy"]
        * np.where(residential_mask, gus_factor, 1.0)
    )
    return bdot_frame


def prepare_sampling_frame(sampling_frame: pd.DataFrame) -> pd.DataFrame:
    """
    - If (Rodzaj_budynku in J/W) & losowania == 'B' → set to 'inny'
    - Keep only 'inny' with general residential names (3 kategorie)
    - latent_area = pow_uzytkowa_m2 * weight * wsp...
    """
    if sampling_frame.empty:
        _logger.warning("prepare_sampling_frame: input sampling_frame is empty.")
        return sampling_frame.copy()

    require_columns(
        sampling_frame,
        [
            COLUMN_BUILDING_TYPE,
            "losowania",
            "nazwa_funkcji_ogolnej",
            "pow_uzytkowa_m2",
            "weight",
            "wspolczynnik_powierzchni_uzytkowej_do_powierzchni_zabudowy",
        ],
        context="prepare_sampling_frame",
    )

    frame = sampling_frame.copy()
    to_other_mask = frame[COLUMN_BUILDING_TYPE].isin(["jednorodzinny", "wielorodzinny"]) & (frame["losowania"] == "B")
    frame.loc[to_other_mask, COLUMN_BUILDING_TYPE] = "inny"

    allowed_general = {
        "Budynki mieszkalne jednorodzinne",
        "Budynki o trzech i więcej mieszkaniach",
        "Budynki o dwóch mieszkaniach i wielomieszkaniowe",
    }
    frame = frame[
        (frame[COLUMN_BUILDING_TYPE] == "inny") & (frame["nazwa_funkcji_ogolnej"].isin(allowed_general))
    ].copy()

    if frame.empty:
        _logger.warning(
            "prepare_sampling_frame: no rows left after filters on Rodzaj_budynku=='inny' "
            "and nazwa_funkcji_ogolnej ∈ allowed_general."
        )
        return frame

    frame["latent_area"] = (
        frame["pow_uzytkowa_m2"] * frame["weight"] * frame["wspolczynnik_powierzchni_uzytkowej_do_powierzchni_zabudowy"]
    )
    return frame


def aggregate_flag(dataframe: pd.DataFrame, flag_column: str) -> pd.DataFrame:
    """
    Group by (Rodzaj_budynku, flag), compute count & area (sum of latent_area),
    map flag to *_connect/*_disconnect, and build 'type'. Returns ['type','count','area'].
    """
    if dataframe.empty:
        _logger.warning("aggregate_flag: dataframe is empty – returning empty summary.")
        return pd.DataFrame(columns=["type", "count", "area"])

    require_columns(
        dataframe,
        [COLUMN_BUILDING_TYPE, flag_column, "latent_area"],
        context=f"aggregate_flag({flag_column})",
    )

    aggregated = (
        dataframe.groupby([COLUMN_BUILDING_TYPE, flag_column], dropna=False)
        .agg(count=(COLUMN_BUILDING_TYPE, "size"), area=("latent_area", "sum"))
        .reset_index()
    )
    flag_label = boolean_to_label(
        aggregated[flag_column],
        f"{flag_column.split('_')[0]}_connect",
        f"{flag_column.split('_')[0]}_disconnect",
    )
    aggregated["type"] = aggregated[COLUMN_BUILDING_TYPE].astype(str) + "_" + flag_label.astype("string")
    return aggregated[["type", "count", "area"]]


def build_residential_area(
    bdot_prepared: pd.DataFrame,
    sampling_prepared: pd.DataFrame,
    key_name: str = "powierzchnia_mieszkalna",
) -> pd.DataFrame:
    """
    Returns a single row with the total residential floor area (sum of latent_area):
    - From BDOT: rows where Rodzaj_budynku in {wielorodzinny, jednorodzinny}.
    - From OPERAT: the entire sampling_prepared dataset (already filtered to general residential).
    """
    if bdot_prepared.empty and sampling_prepared.empty:
        _logger.warning("build_residential_area: both bdot_prepared and sampling_prepared are empty.")

    if not bdot_prepared.empty:
        require_columns(
            bdot_prepared,
            [COLUMN_BUILDING_TYPE, "latent_area"],
            context="build_residential_area – bdot_prepared",
        )
    if not sampling_prepared.empty:
        require_columns(
            sampling_prepared,
            ["latent_area"],
            context="build_residential_area – sampling_prepared",
        )

    residential_mask_bdot = (
        bdot_prepared[COLUMN_BUILDING_TYPE].isin(["wielorodzinny", "jednorodzinny"])
        if not bdot_prepared.empty
        else pd.Series([], dtype=bool)
    )
    area_bdot = float(bdot_prepared.loc[residential_mask_bdot, "latent_area"].sum()) if not bdot_prepared.empty else 0.0
    area_sampling = float(sampling_prepared["latent_area"].sum()) if not sampling_prepared.empty else 0.0

    total_area = area_bdot + area_sampling
    output = pd.DataFrame(
        {"global_par": [key_name], "global_value": [total_area]},
        dtype="object",
    )
    return output


# ---------------------------
# Orchestration
# ---------------------------


def run_find_global_values(
    engine: Engine,
    config: PostprocessingConfig,
    output_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Compute global residential-area values using BDOT and sampling frames.

    Args:
        engine: SQLAlchemy engine for database connection.
        config: PostprocessingConfig instance.
        output_dir: Optional output directory for caching results to CSV.

    Returns:
        DataFrame with global values.
    """
    cache_path = None
    if output_dir:
        cache_path = output_dir / GLOBAL_VALUES_FILENAME
        if cache_path.exists():
            _logger.info("Loading global_values from cached file: %s", cache_path)
            return pd.read_csv(cache_path)

    params = config.params
    gus_factor = float(params.gus_factor)

    bdot_frame, sampling_frame = read_global_inputs(engine)

    bdot_prepared = prepare_bdot_frame(bdot_frame, gus_factor=gus_factor)
    sampling_prepared = prepare_sampling_frame(sampling_frame)

    output = build_residential_area(
        bdot_prepared,
        sampling_prepared,
        key_name="powierzchnia_mieszkalna",
    )

    if cache_path:
        output.to_csv(cache_path, index=False)
        _logger.info("Cached global_values to: %s", cache_path)

    _logger.info("Computed find_global_values - returning DataFrame.")
    return output
