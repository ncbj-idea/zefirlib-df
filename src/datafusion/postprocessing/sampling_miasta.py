from __future__ import annotations

import logging
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from datafusion.configs.postprocessing_config import ColumnsConfig, PostprocessingConfig
from datafusion.constants import TABLE_BUILDING_INVENTORY, TABLE_OPERAT_LOSOWANIA, TABLE_SAMPLED_BUILDINGS
from datafusion.postprocessing.helpers.helpers_sampling_miasta import (
    add_latent_area,
    add_strata_label,
    apply_filters,
    fill_power_columns,
    normalize_size_map,
    pps_multiway,
    strata_multiway_cubeish,
)
from datafusion.utils.crud import load_dataframe_from_db, save_dataframe_to_db
from datafusion.utils.validation import require_columns

_logger = logging.getLogger(__name__)

# ---------------------------
# Config I/O + Inputs
# ---------------------------


def read_inputs_sampling(engine: Engine) -> tuple[pd.DataFrame]:
    """
    Returns: sampling_frame, sampling_input_path, inventory_output_path, sample_output_path.
    """

    sampling_frame = load_dataframe_from_db(engine, TABLE_OPERAT_LOSOWANIA)

    if sampling_frame.empty:
        raise ValueError("read_inputs_sampling: input operat_losowania.xlsx is empty")

    return sampling_frame


# ---------------------------
# Inventory + reports
# ---------------------------


def make_inventory_df(sample_frame: pd.DataFrame, config: PostprocessingConfig, columns: ColumnsConfig) -> pd.DataFrame:
    """One row per merged_id, choose max pow_uzytkowa_m2 within id."""
    if sample_frame.empty:
        _logger.warning("make_inventory_df: sample_frame is empty.")
        keep_columns = [
            columns.merged_id,
            columns.street,
            columns.house_no,
            columns.geom_wkt,
            columns.funk_ogolna,
        ]
        keep_columns = [c for c in keep_columns if c]
        return pd.DataFrame(columns=keep_columns)

    keep_columns = [
        columns.merged_id,
        columns.street,
        columns.house_no,
        columns.geom_wkt,
        columns.funk_ogolna,
    ]

    require_columns(
        sample_frame,
        [columns.merged_id],
        context="make_inventory_df(merged_id)",
    )

    dataframe = sample_frame.copy().dropna(subset=[columns.merged_id])

    area_column = columns.pow_uzytkowa
    if area_column and area_column in dataframe.columns:
        dataframe = dataframe.sort_values([columns.merged_id, area_column], ascending=[True, False])
    else:
        dataframe = dataframe.sort_values([columns.merged_id])

    dataframe = dataframe.drop_duplicates(subset=[columns.merged_id], keep="first")
    dataframe = dataframe.loc[:, [c for c in keep_columns if c in dataframe.columns]].copy()

    for new_column in config.output.add_empty_inventory_cols:
        if new_column not in dataframe.columns:
            dataframe[new_column] = pd.NA
    return dataframe


def assign_surveyors_by_street(
    inventory_frame: pd.DataFrame, config: PostprocessingConfig, columns: ColumnsConfig
) -> pd.DataFrame:
    """Round-robin within each street."""
    if inventory_frame.empty:
        _logger.warning("assign_surveyors_by_street: inventory_frame is empty.")
        return inventory_frame.copy()

    street_column = columns.street
    require_columns(inventory_frame, [street_column], context="assign_surveyors_by_street")

    inventory_assignment = config.inventory_assignment
    num_surveyors = int(inventory_assignment.num_surveyors)
    label_prefix = str(inventory_assignment.label_prefix)
    start_label = int(inventory_assignment.start_label)
    labels = [f"{label_prefix}{i}" for i in range(start_label, start_label + num_surveyors)]
    output = inventory_frame.copy()
    output["__row_index_within_street"] = output.groupby(street_column).cumcount()
    output["przydzial"] = output["__row_index_within_street"].map(lambda k: labels[k % num_surveyors])
    output = output.drop(columns="__row_index_within_street")
    return output


def summarize_sample_by_kind(
    sample_frame: pd.DataFrame,
    kind_col: str = "Rodzaj_budynku",
    weight_col: str = "latent_area",
) -> pd.DataFrame:
    """Summary by building kind in the sample."""
    if sample_frame.empty:
        return pd.DataFrame(columns=[kind_col, "n", "w_sum", "w_share"])

    require_columns(
        sample_frame,
        [kind_col, weight_col],
        context="summarize_sample_by_kind",
    )

    grouped = (
        sample_frame.groupby(kind_col, dropna=False).agg(n=(kind_col, "size"), w_sum=(weight_col, "sum")).reset_index()
    )
    total_weight = grouped["w_sum"].sum()
    grouped["w_share"] = (grouped["w_sum"] / total_weight) if total_weight else 0.0
    return grouped.sort_values(["w_share", "w_sum", "n"], ascending=False, ignore_index=True)


def balance_quality(
    pop_df: pd.DataFrame,
    sample_df: pd.DataFrame,
    marginal_strata: list[str],
    aux_vars: list[str],
    weight_col: str = "latent_area",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Balance quality:
      - for each categorical marginal (each level): ratio = sum_w(sample, level) / sum_w(pop, level)
      - for each numeric aux var: ratio = sum(sample w*x) / sum(pop w*x)
    """
    if pop_df.empty or sample_df.empty:
        _logger.warning(
            "balance_quality: pop_df or sample_df is empty (pop=%d, sample=%d).",
            len(pop_df),
            len(sample_df),
        )

    if not pop_df.empty:
        require_columns(
            pop_df,
            [weight_col] + list(marginal_strata) + list(aux_vars),
            context="balance_quality(pop_df)",
        )
    if not sample_df.empty:
        require_columns(
            sample_df,
            [weight_col] + list(marginal_strata) + list(aux_vars),
            context="balance_quality(sample_df)",
        )

    marginal_rows = []
    for variable in marginal_strata or []:
        pop = pop_df.groupby(variable, dropna=False)[weight_col].sum().rename("pop_w")
        smp = sample_df.groupby(variable, dropna=False)[weight_col].sum().rename("sample_w")
        both = pd.concat([pop, smp], axis=1).fillna(0.0).reset_index()
        both["variable"] = variable
        both["ratio"] = both.apply(
            lambda r: (r["sample_w"] / r["pop_w"]) if r["pop_w"] else np.nan,
            axis=1,
        )
        both = both.rename(columns={variable: "level"})
        marginal_rows.append(both[["variable", "level", "pop_w", "sample_w", "ratio"]])
    df_marginal = (
        pd.concat(marginal_rows, ignore_index=True)
        if marginal_rows
        else pd.DataFrame(columns=["variable", "level", "pop_w", "sample_w", "ratio"])
    )

    aux_rows = []
    for variable in aux_vars or []:
        pop_wx = float((pop_df.get(variable, pd.Series(0.0)) * pop_df[weight_col]).sum(skipna=True))
        smp_wx = float((sample_df.get(variable, pd.Series(0.0)) * sample_df[weight_col]).sum(skipna=True))
        ratio = (smp_wx / pop_wx) if pop_wx not in (0.0, None) and pd.notna(pop_wx) else np.nan
        aux_rows.append(
            {
                "variable": variable,
                "pop_wx": pop_wx,
                "sample_wx": smp_wx,
                "ratio": ratio,
            }
        )
    df_aux = pd.DataFrame(aux_rows, columns=["variable", "pop_wx", "sample_wx", "ratio"])
    return df_marginal, df_aux


# ---------------------------
# Orchestration
# ---------------------------


def run_sampling_miasta(
    base_directory: Path,
    engine: Engine,
    config: PostprocessingConfig,
) -> None:
    _logger.info("Starting sampling_miasta part.")
    try:
        columns = config.columns
        sampling_config = config.sampling

        sampling_frame = read_inputs_sampling(engine)
        _logger.info("Number of lines in the input file: %d", len(sampling_frame))

        sampling_frame = apply_filters(sampling_frame, config, columns)
        _logger.info("Number of rows after filters: %d", len(sampling_frame))

        if sampling_frame.empty:
            raise RuntimeError("run_sampling_miasta: no rows left after applying filters – aborting.")

        sampling_frame = fill_power_columns(sampling_frame, columns)

        strata_column = sampling_config.strata_col
        multiway_columns = sampling_config.multiway_cols

        require_columns(
            sampling_frame,
            [strata_column, columns.rodzaj_budynku],
            context="run_sampling_miasta – base columns",
        )

        levels_alpha = sorted(sampling_frame[strata_column].dropna().astype(str).unique().tolist())
        _logger.info("Available building divisions (by filters): %s", levels_alpha)

        building_type_column = columns.rodzaj_budynku

        by_building_kind = (
            sampling_frame[building_type_column]
            .astype(str)
            .str.strip()
            .str.lower()
            .replace({"": np.nan})
            .value_counts(dropna=False)
            .rename_axis(building_type_column)
            .reset_index(name="N")
        )

        _logger.info(
            "Liczebności wg %s (po filtrach):\n%s",
            building_type_column,
            by_building_kind.to_string(index=False),
        )

        sampling_frame = add_strata_label(sampling_frame, columns)
        sampling_frame = add_latent_area(sampling_frame, columns)

        require_columns(
            sampling_frame,
            ["Rodzaj_budynku", "latent_area"],
            context="run_sampling_miasta – latent summary",
        )

        latent_summary = (
            sampling_frame.groupby("Rodzaj_budynku", dropna=False)
            .agg(
                N=("Rodzaj_budynku", "size"),
                latent_sum=("latent_area", "sum"),
                latent_pos=("latent_area", lambda s: (s > 0).sum()),
            )
            .reset_index()
        )
        _logger.info("Latent_area per stratum:\n%s", latent_summary.to_string(index=False))

        _logger.info(
            "CFG sampling.size_by_stratum (raw): %s",
            sampling_config.size_by_stratum,
        )
        _logger.info("CFG sampling.size_vector (raw): %s", sampling_config.size_vector)

        size_map = normalize_size_map(sampling_frame, strata_column, sampling_config.size_by_stratum)
        _logger.info("size_by_stratum used (normalized): %s", size_map)

        levels = sorted(sampling_frame[strata_column].dropna().astype(str).str.strip().str.lower().unique().tolist())
        level_fraction_pairs = {level: size_map.get(level, None) for level in levels}
        _logger.info("Levels → fractions: %s", level_fraction_pairs)

        frame_for_sampling = pps_multiway(
            data=sampling_frame,
            strata_col=strata_column,
            multiway_cols=multiway_columns,
            size_variable="latent_area",
            size_by_stratum=size_map,
            size_vector=sampling_config.size_vector,
        )

        sampled_frame = strata_multiway_cubeish(
            data=frame_for_sampling,
            pik_col="prob",
            strata_col=strata_column,
            marginal_strata=multiway_columns,
            aux_vars=sampling_config.aux_vars,
            seed=int(sampling_config.cube_seed),
            iters=int(sampling_config.balance_iters),
        )

        sample_flag_column = columns.sample_flag
        if sample_flag_column not in sampled_frame.columns:
            raise KeyError(f"Missing column '{sample_flag_column}' in sampling result.")
        sampled_frame = sampled_frame.loc[sampled_frame[sample_flag_column] > (1 - 1e-6)].copy()
        _logger.info("Liczba wierszy pozostawiona (sample_ind≈1): %d", len(sampled_frame))

        by_building_kind_sample = summarize_sample_by_kind(
            sampled_frame,
            kind_col=sampling_config.strata_col or "Rodzaj_budynku",
            weight_col="latent_area",
        )
        _logger.info(
            "Zestawienie próby wg rodzaju budynku (top 10):\n%s",
            by_building_kind_sample.head(10).to_string(index=False),
        )

        df_marg_ratio, df_aux_ratio = balance_quality(
            pop_df=sampling_frame,
            sample_df=sampled_frame,
            marginal_strata=multiway_columns,
            aux_vars=sampling_config.aux_vars,
            weight_col="latent_area",
        )
        if not df_marg_ratio.empty:
            _logger.info(
                "Balans (marginale): średni ratio=%.4f, mediana=%.4f",
                df_marg_ratio["ratio"].mean(skipna=True),
                df_marg_ratio["ratio"].median(skipna=True),
            )
        if not df_aux_ratio.empty:
            _logger.info("Balans (aux):\n%s", df_aux_ratio.to_string(index=False))

        inventory_frame = make_inventory_df(sampled_frame.copy(), config, columns)
        inventory_frame = assign_surveyors_by_street(inventory_frame, config, columns)
        save_dataframe_to_db(engine, inventory_frame, TABLE_BUILDING_INVENTORY)
        save_dataframe_to_db(engine, sampled_frame, TABLE_SAMPLED_BUILDINGS)
        base_directory.mkdir(parents=True, exist_ok=True)
        inventory_frame.to_excel(base_directory / "inwentaryzacja.xlsx", index=False, engine="openpyxl")
        sampled_frame.to_excel(base_directory / "wylosowane.xlsx", index=False, engine="openpyxl")

        _logger.info("Saved inwentaryzacja")
        _logger.info("Saved wylosowane")
        _logger.info("Ended part of sampling_miasta.")

    except (ValueError, RuntimeError) as e:
        _logger.error(f"Expected error in sampling pipeline: {e}")
        raise
    except Exception:
        _logger.exception("Unexpected pipeline failure")
        traceback.print_exc()
        raise
