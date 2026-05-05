"""Pipeline orchestration for BDOT modification.

This module composes lower-level helpers into the `BdotModificationPipeline`
class used by `MergeReader`. It processes and merges building data from BDOT
(Baza Danych Obiektów Topograficznych - Database of Topographic Objects).
It includes functionality for:

- Geometry processing and coordinate transformations
- H3 spatial indexing for buildings
- Multi-criteria evaluation using synthetic indices
- Building merging based on address and proximity
- Heat network connectivity analysis

Coordinate System Assumptions:
    - Input geometries are expected in EPSG:2180 (Polish national grid)
    - H3 indexing requires transformation to EPSG:4326 (WGS84 lat/lon)
    - Distance calculations assume EPSG:2180 units (meters)

Key Pipeline:
    1. Data cleaning (simple_bdot_clean)
    2. H3 spatial indexing (add_h3)
    3. Evaluation metrics calculation (prep_to_evaluation)
    4. Synthetic index calculation (miernik_syntetyczny)
    5. Building categorization and merging
    6. Final dataset assembly (BdotModificationPipeline)
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from datafusion.configs.merge_config import MergeConfig
from datafusion.constants import COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN

from .constants import POSITIVE_CLASSIFICATION_LABELS
from .evaluation import miernik_syntetyczny, prep_to_evaluation
from .h3_utils import _compute_h3_from_geometries, _validate_h3_resolution
from .helpers import (
    _optimize_string_columns_to_categorical,
    _to_bool_series,
    _validate_coordinate_system,
    _validate_dataframe_not_empty,
)
from .merge_utils import (
    conditional_split_building,
    create_pyszny_bdot,
    divide_inw_bdot,
    merge_building,
)

logger = logging.getLogger(__name__)


class BdotModificationPipeline:
    """Pipeline wrapper for BDOT modification functions.

    The class mirrors the original `BdotModificationPipeline` but composes
    the functions implemented in smaller modules.
    """

    def __init__(self, config: MergeConfig) -> None:  # type: ignore[name-defined]
        self.config = config
        self.bdot_params = config.bdot_params

    def run(self, data: pd.DataFrame) -> pd.DataFrame:
        _validate_dataframe_not_empty(data, "Input data for BDOT pipeline")

        cfg = self.config
        bp = self.bdot_params
        col_keep = list(bp.bdot_col_output)

        # Step 1: cleaning
        bdot = self.simple_bdot_clean(data=data)

        # Step 2: H3 assignment (delegates to helper)
        bdot_prep = self.add_h3(data=bdot)

        # Step 3 & 4 & 5 handled similarly to original file by calling evaluation helpers
        bdot_clss = prep_to_evaluation(
            data=bdot_prep,
            heat_ind=bp.bdot_heat,
            area=bp.bdot_pow_uzytkow,
            h3_col=cfg.h3_name,
            heat_dist=bp.heat_distance,
            gini_indicator=cfg.gini_in_topsis,
            lorenz_gini=cfg.gini_lorenz,
            method_gini=cfg.gini_method,
        )

        final_results = miernik_syntetyczny(
            data=bdot_clss,
            var_stymulanta=["heat_connectivity", "neighbor"],
            classification=True,
            method=cfg.classification_method,
        )

        razem = self.prep_final_h3(
            data_h3=bdot_prep,
            data_res=final_results,
            bdot_data=bdot,
        )

        # Steps 6 & 7 delegated to merge_utils
        extra_cols = [
            bp.bdot_id,
            bp.bdot_pow_uzytkow,
            bp.bdot_obrys,
            bp.bdot_addr_distance,
            bp.bdot_street_col,
            bp.bdot_number_col,
            *bp.bdot_binary_var,
            bp.bdot_geom_var,
            bp.bdot_merge_var,
            COLUMN_FUNCTIONAL_CATEGORY_TOP_DOWN,
        ]
        for col in extra_cols + bp.bdot_col_output:
            if col not in col_keep:
                col_keep.append(col)

        bdot_divided = divide_inw_bdot(
            data=razem,
            divide_var=bp.bdot_detail,
            divide_values=bp.non_inventory_build,
            col_to_keep=col_keep,
            ulica=bp.bdot_street_col,
            numer=bp.bdot_number_col,
        )

        list_bdot = conditional_split_building(
            data=bdot_divided["bdot_included"],
            cond1=bp.bdot_merge_var,
            living=bp.living_bdot,
            geom=bp.bdot_geom_var,
            id=bp.bdot_id,
            addr_distance=bp.bdot_addr_distance,
        )

        final_living = merge_building(
            data=list_bdot["living"],
            merge_var=bp.bdot_merge_var,
            id=bp.bdot_id,
            geom=bp.bdot_geom_var,
            bdot_key="bdot_key",
            addr_distance=bp.bdot_addr_distance,
            aggr_var=bp.bdot_sum_var,
            addr_var=bp.bdot_addr_var,
            bin_var=bp.bdot_binary_var,
            living=True,
            log_file=cfg.expanded_logs,
        )

        final_non_living = merge_building(
            data=list_bdot["non_living"],
            merge_var=bp.bdot_merge_var,
            id=bp.bdot_id,
            geom=bp.bdot_geom_var,
            bdot_key="bdot_key",
            addr_distance=bp.bdot_addr_distance,
            aggr_var=bp.bdot_sum_var,
            addr_var=bp.bdot_addr_var,
            bin_var=bp.bdot_binary_var,
            living=False,
            complex_distance=cfg.complex_distance,
            log_file=cfg.expanded_logs,
        )

        pyszny_bdot = create_pyszny_bdot(
            data_ready=list_bdot["ready_data"],
            data_living=final_living,
            data_nonliving=final_non_living,
            data_excluded=bdot_divided["bdot_excluded"],
        )

        if len(pyszny_bdot) > 10000:
            pyszny_bdot = _optimize_string_columns_to_categorical(
                pyszny_bdot,
                columns=[
                    "status",
                    "inwentaryzacja",
                    "classification",
                    "h3_connectivity",
                ],
            )  # pragma: no cover

        return pyszny_bdot

    # Small helpers kept as methods to avoid circular imports
    def simple_bdot_clean(
        self,
        data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Clean BDOT dataframe using column names from `self.bdot_params`."""
        bp = self.bdot_params
        street = bp.bdot_street_col
        floor = bp.bdot_floors
        pow_uzytk = bp.bdot_pow_uzytkow
        pow_area = bp.bdot_obrys

        df = data.copy()
        if street in df.columns:
            df[street] = df[street].astype(str).str.replace(r"^al\\.", "aleja", regex=True)
        if floor in df.columns:
            df[floor] = df[floor].fillna(1)
        else:
            df[floor] = 1
        if pow_area in df.columns:
            df[pow_uzytk] = df.get(pow_area, pd.Series([pd.NA] * len(df))).astype(float) * df[floor].astype(float)
        return df

    def add_h3(
        self,
        data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Compute H3 index for buildings using defaults from `self.config`/`self.bdot_params`."""
        _validate_dataframe_not_empty(data, "Input data for H3 indexing")

        bp = self.bdot_params
        cfg = self.config
        detail_build = bp.bdot_detail
        exluded_build = bp.h3_excluded_type
        geom_var = bp.bdot_geom_var
        coord_name = cfg.coord_system
        h3_col = cfg.h3_name
        resolution = cfg.h3_resolution

        _validate_h3_resolution(resolution)
        _validate_coordinate_system(coord_name)

        df = data.copy()
        initial_count = len(df)
        if detail_build in df.columns:
            mask = ~df[detail_build].isin(list(exluded_build))
            df = df.loc[mask].copy()
            logger.info(f"Filtered {initial_count - len(df)} buildings with excluded types. Remaining: {len(df)}")

        geom_series = df.get(geom_var, pd.Series(index=df.index, dtype=str))
        h3_series = _compute_h3_from_geometries(geom_series, coord_name, resolution)
        df[h3_col] = h3_series
        logger.info(f"Successfully computed H3 index for {h3_series.notna().sum()}/{len(h3_series)} buildings")
        return df

    def prep_final_h3(
        self,
        data_h3: pd.DataFrame,
        data_res: pd.DataFrame,
        bdot_data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Prepare final H3-joined dataframe using defaults from `self.config`/`self.bdot_params`."""
        cfg = self.config
        bp = self.bdot_params
        join_h3 = cfg.h3_name
        bdot_id = bp.bdot_id
        geom_var = bp.bdot_geom_var
        coord_system = cfg.coord_system
        h3_resolution = cfg.h3_resolution
        bdot_heat = bp.bdot_heat

        final_data = data_h3.copy()
        final_data = final_data.merge(data_res, how="left", left_on=join_h3, right_on=join_h3)
        missing_mask = final_data["classification"].isna()
        if missing_mask.any():
            geom_series = bdot_data.get(geom_var, pd.Series(index=bdot_data.index, dtype=str))
            calc_h3 = _compute_h3_from_geometries(geom_series, coord_system, h3_resolution)
            temp_h3 = pd.DataFrame(
                {
                    bdot_id: bdot_data.get(bdot_id, pd.Series(range(len(bdot_data)))),
                    join_h3: calc_h3,
                }
            )
            lookup = data_res[[join_h3, "index", "classification"]].drop_duplicates()
            # Map H3 -> classification/index to avoid an extra merge
            h3_to_class = lookup.set_index(join_h3)["classification"]
            h3_to_index = lookup.set_index(join_h3)["index"]
            temp_h3["classification"] = temp_h3[join_h3].map(h3_to_class)
            temp_h3["index"] = temp_h3[join_h3].map(h3_to_index)
            if bdot_id in final_data.columns and bdot_id in temp_h3.columns:
                # Build mapping bdot_id -> classification/index from temp_h3 and fill missing values
                id_to_class = temp_h3.set_index(bdot_id)["classification"]
                id_to_index = temp_h3.set_index(bdot_id)["index"]
                missing = final_data["classification"].isna()
                if missing.any():
                    final_data.loc[missing, "classification"] = final_data.loc[missing, bdot_id].map(id_to_class)
                    final_data.loc[missing, "index"] = final_data.loc[missing, bdot_id].map(id_to_index)
        # Compute boolean mask for positive classifications once and reuse
        class_series = final_data["classification"].isin(POSITIVE_CLASSIFICATION_LABELS).fillna(False)
        class_arr = class_series.to_numpy(dtype=bool)

        if bdot_heat and bdot_heat in final_data.columns:
            # Compute boolean mask for heat from provided column (if present)
            heat_series = _to_bool_series(final_data[bdot_heat])
            heat_arr = heat_series.to_numpy(dtype=bool)

            # Single assignment using NumPy logical_or to avoid multiple Series temporaries
            final_data["h3_connectivity"] = np.logical_or(heat_arr, class_arr)
        else:
            final_data["h3_connectivity"] = class_arr
        return final_data


__all__ = ["BdotModificationPipeline"]
