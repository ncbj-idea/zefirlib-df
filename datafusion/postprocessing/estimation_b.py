from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from datafusion.configs.postprocessing_config import PostprocessingConfig
from datafusion.postprocessing.helpers.helpers_estimations import (
    pps_systematic,
    raking_calibration,
    read_estimations_inputs,
    survey_ratio_point,
    survey_weighted_sum_table,
    translate_heat_source_column,
)
from datafusion.utils.crud import save_dataframe_to_db
from datafusion.utils.validation import require_columns

# ---------------------------
# Estimation_B
# ---------------------------


class EstimationB:
    def __init__(self, engine: Engine, config: PostprocessingConfig, global_values: pd.DataFrame):
        self.engine = engine
        self.config = config
        self.global_values = global_values

        columns_config = config.columns
        self.usable_area_column = columns_config.pow_uzytkowa
        self.footprint_area_column = columns_config.pow_obrysu
        self.weight_column = columns_config.weight
        self.building_type_column = columns_config.rodzaj_budynku
        self.central_heating_column = columns_config.centralne
        self.hot_water_column = columns_config.cwu
        self.h3_sampling_column = columns_config.h3
        self.h3_estimation_column = columns_config.h3_estimation or self.h3_sampling_column

        params_config = config.params
        self.gus_factor = params_config.gus_factor
        self.krakow_factor = params_config.krakow_factor
        self.hex_size = float(params_config.hex_size)
        self.heat_strat_column = params_config.heat_strat
        self.pv_power = float(params_config.pv_power)
        self.non_residential_pv_factor = params_config.niemieszkalne_pv

        self.seed_h3 = int(params_config.seed_h3)
        self.seed_operat = int(params_config.seed_open or params_config.seed_operat or 789)
        self.seed_termo = int(params_config.seed_term or params_config.seed_termo or 542)

        self.raking_bounds_operat = params_config.raking_bounds_operat_b
        self.raking_bounds_termo = params_config.raking_bounds_termo_b

        self.calibrate_area = bool(params_config.calib_area)
        self.calibrate_heat = bool(params_config.calib_heat)
        self.calibrate_gas = bool(params_config.calib_gas)

        self.building_types = ("inny", "biuro", "handlowy")

        self.calibration_operat: dict[str, float] = {}
        self.calibration_termo: dict[str, float] = {}

    # ───────── Read inputs ─────────

    def load_inputs(self) -> None:
        """Load inputs"""
        data = read_estimations_inputs(self.engine)

        self.operat_raw = data["operat"].copy()
        self.termo_raw = data["estimation"].copy()

        if self.operat_raw.empty:
            raise ValueError("EstimationB.load_inputs: operat dataframe is empty.")
        if self.termo_raw.empty:
            raise ValueError("EstimationB.load_inputs: estimation/termo dataframe is empty.")

    # ───────── latent_area ─────────

    def compute_latent_area(self) -> None:
        """
        Compute latent area for operat and termo dataframes after validating inputs,
        filtering by building types, and applying Kraków and ratio adjustments.

        Updates self.operat and self.termo with computed latent areas
        and constructed strata.
        """
        operat_dataframe = self.operat_raw.copy()
        termo_dataframe = self.termo_raw.copy()

        require_columns(
            operat_dataframe,
            [self.usable_area_column, self.building_type_column],
            context="EstimationB.compute_latent_area – operat",
        )
        if not termo_dataframe.empty:
            require_columns(
                termo_dataframe,
                [self.usable_area_column, self.building_type_column],
                context="EstimationB.compute_latent_area – termo",
            )

        operat_dataframe[self.weight_column] = operat_dataframe.get(self.weight_column, 1.0).fillna(1.0)

        operat_dataframe = operat_dataframe[
            operat_dataframe[self.building_type_column].isin(self.building_types)
        ].copy()
        termo_dataframe = termo_dataframe[termo_dataframe[self.building_type_column].isin(self.building_types)].copy()

        if operat_dataframe.empty:
            raise ValueError("EstimationB.compute_latent_area: no rows in operat after filtering to building_types.")

        ratio_column = "usable_area_to_built-up_area_ratio"
        for dataframe in (operat_dataframe, termo_dataframe):
            if dataframe.empty:
                continue
            if ratio_column not in dataframe.columns:
                dataframe[ratio_column] = 1.0
            dataframe["latent_area"] = (
                dataframe[self.usable_area_column].astype(float)
                * float(self.krakow_factor)
                * dataframe[ratio_column].astype(float)
            )

        if self.heat_strat_column not in operat_dataframe.columns:
            operat_dataframe[self.heat_strat_column] = ""
        operat_dataframe["strata"] = (
            operat_dataframe[self.building_type_column].astype(str)
            + "_"
            + operat_dataframe[self.central_heating_column].astype(str)
            + "_"
            + operat_dataframe[self.heat_strat_column].astype(str)
        )

        self.operat = operat_dataframe.reset_index(drop=True)
        self.termo = termo_dataframe.reset_index(drop=True)

    # ───────── Global vectors ─────────

    def build_global_calibration_vectors(self) -> None:
        """
        Build calibration targets and wide-format design variables for area, heat and
        gas based on global values and operat/termo data.
        """
        global_values_dataframe = self.global_values.copy()

        require_columns(
            global_values_dataframe,
            ["global_par", "global_value"],
            context="EstimationB.build_global_calibration_vectors – global_values",
        )

        if self.calibrate_area:
            mask = global_values_dataframe["global_par"].astype(str).str.contains(r"\d") & global_values_dataframe[
                "global_par"
            ].astype(str).str.contains("handlowy|^inny|biuro")
            hex_dataframe = global_values_dataframe.loc[mask, ["global_par", "global_value"]].copy()

            def _strata_from_parameter(parameter: str) -> str:
                if "inny" in parameter:
                    return "inny"
                if "biuro" in parameter:
                    return "biuro"
                return "handlowy"

            hex_dataframe["strata"] = hex_dataframe["global_par"].astype(str).map(_strata_from_parameter)

            rng = np.random.default_rng(self.seed_h3)
            chosen_indices: list[int] = []
            for _, group in hex_dataframe.groupby("strata", observed=True, dropna=False):
                n_group = max(1, int(np.floor(len(group) * self.hex_size)))
                sizes = group["global_value"].to_numpy(dtype=float)
                mask_selected = pps_systematic(sizes, n=n_group, rng=rng)
                chosen_indices.extend(group.index[mask_selected].tolist())

            chosen_hex = hex_dataframe.loc[chosen_indices]
            logging.info(
                "B: PPS selected %d/%d hexes (hex_size=%.2f).",
                len(chosen_hex),
                len(hex_dataframe),
                self.hex_size,
            )

            global_hex = pd.Series(
                chosen_hex["global_value"].to_numpy(),
                index=chosen_hex["global_par"].astype(str),
            ).to_dict()
            self.calibration_operat.update(global_hex)

            if self.h3_estimation_column in self.operat.columns:
                h3_column = self.h3_estimation_column
            elif self.h3_sampling_column in self.operat.columns:
                h3_column = self.h3_sampling_column
                logging.warning(
                    "B: columns.h3_estimation not found – using columns.h3 = '%s'.",
                    h3_column,
                )
            else:
                h3_column = None
                logging.warning("B: Missing H3 column – skipping H3-based pivot.")

            if h3_column is not None:
                operat_dataframe = self.operat.copy()
                operat_dataframe["temp_ll"] = (
                    operat_dataframe[self.building_type_column].astype(str)
                    + "_"
                    + operat_dataframe[h3_column].astype(str)
                )
                operat_dataframe["latent_area2"] = operat_dataframe["latent_area"]
                wide_operat = operat_dataframe.pivot_table(
                    index=operat_dataframe.index,
                    columns="temp_ll",
                    values="latent_area2",
                    aggfunc="sum",
                    fill_value=0.0,
                )
                self.operat = pd.concat(
                    [operat_dataframe.drop(columns=["latent_area2"]), wide_operat],
                    axis=1,
                )

        if self.calibrate_heat:
            mask = global_values_dataframe["global_par"].astype(str).str.contains(
                r"heat_.+_area"
            ) & global_values_dataframe["global_par"].astype(str).str.contains("handlowy|^inny|biuro")
            area_dataframe = global_values_dataframe.loc[mask, ["global_par", "global_value"]].copy()
            self.calibration_operat.update(
                pd.Series(
                    area_dataframe["global_value"].to_numpy(),
                    index=area_dataframe["global_par"].astype(str),
                ).to_dict()
            )

            operat_dataframe = self.operat.copy()
            if "heat_connected" not in operat_dataframe.columns:
                operat_dataframe["heat_connected"] = False
            operat_dataframe["temp_ll"] = (
                operat_dataframe[self.building_type_column].astype(str)
                + "_"
                + np.where(
                    operat_dataframe["heat_connected"],
                    "heat_connect",
                    "heat_disconnect",
                )
                + "_area"
            )
            operat_dataframe["latent_area2"] = operat_dataframe["latent_area"]
            wide_operat = operat_dataframe.pivot_table(
                index=operat_dataframe.index,
                columns="temp_ll",
                values="latent_area2",
                aggfunc="sum",
                fill_value=0.0,
            )
            self.operat = pd.concat([operat_dataframe.drop(columns=["latent_area2"]), wide_operat], axis=1)

            termo_dataframe = self.termo.copy()
            if not termo_dataframe.empty:
                if "heat_connected" not in termo_dataframe.columns:
                    termo_dataframe["heat_connected"] = False
                termo_dataframe["temp_ll"] = (
                    termo_dataframe[self.building_type_column].astype(str)
                    + "_"
                    + np.where(
                        termo_dataframe["heat_connected"],
                        "heat_connect",
                        "heat_disconnect",
                    )
                    + "_area"
                )
                termo_dataframe["latent_area2"] = termo_dataframe["latent_area"]
                wide_termo = termo_dataframe.pivot_table(
                    index=termo_dataframe.index,
                    columns="temp_ll",
                    values="latent_area2",
                    aggfunc="sum",
                    fill_value=0.0,
                )
                self.termo = pd.concat([termo_dataframe.drop(columns=["latent_area2"]), wide_termo], axis=1)

        if self.calibrate_gas:
            mask = global_values_dataframe["global_par"].astype(str).str.contains(
                r"gas_.+_area"
            ) & global_values_dataframe["global_par"].astype(str).str.contains("handlowy|^inny|biuro")
            area_dataframe = global_values_dataframe.loc[mask, ["global_par", "global_value"]].copy()
            self.calibration_operat.update(
                pd.Series(
                    area_dataframe["global_value"].to_numpy(),
                    index=area_dataframe["global_par"].astype(str),
                ).to_dict()
            )

            operat_dataframe = self.operat.copy()
            if "gas_connected" not in operat_dataframe.columns:
                operat_dataframe["gas_connected"] = False
            operat_dataframe["temp_ll"] = (
                operat_dataframe[self.building_type_column].astype(str)
                + "_"
                + np.where(
                    operat_dataframe["gas_connected"],
                    "gas_connect",
                    "gas_disconnect",
                )
                + "_area"
            )
            operat_dataframe["latent_area2"] = operat_dataframe["latent_area"]
            wide_operat = operat_dataframe.pivot_table(
                index=operat_dataframe.index,
                columns="temp_ll",
                values="latent_area2",
                aggfunc="sum",
                fill_value=0.0,
            )
            self.operat = pd.concat([operat_dataframe.drop(columns=["latent_area2"]), wide_operat], axis=1)

            termo_dataframe = self.termo.copy()
            if not termo_dataframe.empty:
                if "gas_connected" not in termo_dataframe.columns:
                    termo_dataframe["gas_connected"] = False
                termo_dataframe["temp_ll"] = (
                    termo_dataframe[self.building_type_column].astype(str)
                    + "_"
                    + np.where(
                        termo_dataframe["gas_connected"],
                        "gas_connect",
                        "gas_disconnect",
                    )
                    + "_area"
                )
                termo_dataframe["latent_area2"] = termo_dataframe["latent_area"]
                wide_termo = termo_dataframe.pivot_table(
                    index=termo_dataframe.index,
                    columns="temp_ll",
                    values="latent_area2",
                    aggfunc="sum",
                    fill_value=0.0,
                )
                self.termo = pd.concat([termo_dataframe.drop(columns=["latent_area2"]), wide_termo], axis=1)

    # ───────── Calibration of operat ─────────

    def calibrate_operat_and_build_super_global(self) -> None:
        """
        Calibrate operat weights by raking and build super-global central-heating
        area totals.
        """
        operat_dataframe = self.operat.copy()

        require_columns(
            operat_dataframe,
            [self.central_heating_column, "latent_area"],
            context="EstimationB.calibrate_operat_and_build_super_global – operat",
        )

        # stałe wagi niestosowności
        operat_dataframe["non_random_weight"] = 3024.0 / 2340.0
        operat_dataframe["non_random_prob"] = 2340.0 / 3024.0

        sample_dataframe = operat_dataframe.loc[~operat_dataframe[self.central_heating_column].isna()].copy()

        if sample_dataframe.empty:
            raise ValueError(
                "EstimationB.calibrate_operat_and_build_super_global: no rows with non-NA central heating info."
            )

        feature_columns = list(self.calibration_operat.keys())
        for column in feature_columns:
            if column not in sample_dataframe.columns:
                sample_dataframe[column] = 0.0

        bounds = None
        if (
            self.raking_bounds_operat
            and isinstance(self.raking_bounds_operat, (list, tuple))
            and len(self.raking_bounds_operat) == 2
        ):
            bounds = (
                float(self.raking_bounds_operat[0]),
                float(self.raking_bounds_operat[1]),
            )

        sample_dataframe["calib_weight_operat_B"] = raking_calibration(
            dataframe=sample_dataframe,
            base_weight_column="non_random_weight",
            feature_columns=feature_columns,
            targets=self.calibration_operat,
            max_iterations=10_000,
            bounds=bounds,
        )

        logging.info(
            "Calibration of B (operat) – weights: min=%.6f, q1=%.6f, med=%.6f, q3=%.6f, max=%.6f",
            float(sample_dataframe["calib_weight_operat_B"].min()),
            float(sample_dataframe["calib_weight_operat_B"].quantile(0.25)),
            float(sample_dataframe["calib_weight_operat_B"].median()),
            float(sample_dataframe["calib_weight_operat_B"].quantile(0.75)),
            float(sample_dataframe["calib_weight_operat_B"].max()),
        )

        central_heating_area = survey_weighted_sum_table(
            dataframe=sample_dataframe.assign(_latent=sample_dataframe["latent_area"]),
            value_column="_latent",
            group_by=[self.building_type_column, self.central_heating_column],
            weight_column="calib_weight_operat_B",
        )
        if not central_heating_area.empty:
            central_heating_area = central_heating_area.loc[central_heating_area["Freq"] != 0].copy()
            central_heating_area["calib_par"] = (
                "centralne_"
                + central_heating_area[self.building_type_column].astype(str)
                + "_"
                + central_heating_area[self.central_heating_column].astype(str).str.replace(" ", "_", regex=False)
            )
            super_global = central_heating_area[["calib_par", "Freq"]].copy()
        else:
            super_global = pd.DataFrame({"calib_par": [], "Freq": []})

        self.super_global = super_global
        logging.info("super_global B: %d calibration positions.", len(super_global))

    # ───────── Final calibration termo + estimation ─────────

    def final_estimation(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Perform final B-estimation: calibrate thermo sample, derive energy and PV
        indicators, and aggregate domain-level results.
        """
        termo_dataframe = self.termo.copy()

        if termo_dataframe.empty:
            raise ValueError("EstimationB.final_estimation: termo dataframe is empty.")

        require_columns(
            termo_dataframe,
            [
                "Klasa_termo",
                "latent_area",
                self.building_type_column,
                self.central_heating_column,
                self.hot_water_column,
                self.footprint_area_column,
            ],
            context="EstimationB.final_estimation – termo",
        )

        def map_termo(thermal_class: str) -> str:
            if thermal_class in ("A", "B"):
                return "AB"
            if thermal_class in ("E", "F"):
                return "EF"
            if thermal_class == "C":
                return "C"
            if thermal_class == "D":
                return "D"
            return "Brak"

        termo_dataframe["zefir_termo"] = termo_dataframe["Klasa_termo"].astype(str).map(map_termo)

        termo_dataframe["yearly_heat_demand"] = (
            termo_dataframe["latent_area"] * termo_dataframe.get("heat", 0.0)
        ).fillna(0.0)
        termo_dataframe["yearly_heat_water_demand"] = (
            termo_dataframe["latent_area"] * termo_dataframe.get("heat_water", 0.0)
        ).fillna(0.0)
        termo_dataframe["yearly_cooling_demand"] = (
            termo_dataframe["latent_area"] * termo_dataframe.get("cold", 0.0)
        ).fillna(0.0)

        final_calibration = pd.Series(
            self.super_global["Freq"].to_numpy(),
            index=self.super_global["calib_par"].astype(str),
        ).to_dict()
        final_calibration = {key.replace(" ", "_"): float(value) for key, value in final_calibration.items()}

        termo_dataframe["rodzaj_cwu"] = (
            "cwu_"
            + termo_dataframe[self.building_type_column].astype(str)
            + "_"
            + termo_dataframe[self.hot_water_column].astype(str)
        )
        termo_dataframe["rodzaj_centralne"] = (
            "centralne_"
            + termo_dataframe[self.building_type_column].astype(str)
            + "_"
            + termo_dataframe[self.central_heating_column].astype(str)
        )

        for name_column in ["rodzaj_cwu", "rodzaj_centralne"]:
            temp_dataframe = termo_dataframe.copy()
            temp_dataframe["latent_tmp"] = temp_dataframe["latent_area"]
            wide = temp_dataframe.pivot_table(
                index=temp_dataframe.index,
                columns=name_column,
                values="latent_tmp",
                aggfunc="sum",
                fill_value=0.0,
            )
            termo_dataframe = pd.concat([termo_dataframe, wide], axis=1)

        termo_dataframe["nominator"] = (
            termo_dataframe[self.building_type_column].astype(str)
            + "_"
            + termo_dataframe["zefir_termo"].astype(str)
            + "_"
            + termo_dataframe[self.central_heating_column].astype(str).str.replace(" ", "_", regex=False)
        )
        termo_dataframe["cwu_nominator"] = (
            termo_dataframe[self.building_type_column].astype(str)
            + "_"
            + termo_dataframe["zefir_termo"].astype(str)
            + "_"
            + termo_dataframe[self.hot_water_column].astype(str).str.replace(" ", "_", regex=False)
        )
        if self.heat_strat_column not in termo_dataframe.columns:
            termo_dataframe[self.heat_strat_column] = ""
        termo_dataframe["heat_nominator"] = (
            termo_dataframe[self.building_type_column].astype(str)
            + "_"
            + termo_dataframe["zefir_termo"].astype(str)
            + "_"
            + termo_dataframe[self.heat_strat_column].astype(str)
        )
        termo_dataframe["denominator"] = (
            termo_dataframe[self.building_type_column].astype(str) + "_" + termo_dataframe["zefir_termo"].astype(str)
        )

        termo_dataframe["max_nominal_power_pv"] = (
            termo_dataframe.get(self.weight_column, 1.0)
            * termo_dataframe[self.footprint_area_column]
            * 0.5
            * float(self.pv_power)
        )
        termo_dataframe["base_nominal_power"] = (
            termo_dataframe.get(self.weight_column, 1.0)
            * termo_dataframe[self.footprint_area_column]
            * float(self.non_residential_pv_factor)
        )

        termo_dataframe["strata_avg"] = (
            termo_dataframe[self.building_type_column].astype(str)
            + "-"
            + termo_dataframe[self.central_heating_column].astype(str)
        )

        termo_dataframe["prob"] = (
            termo_dataframe.get("prob", pd.Series(1.0, index=termo_dataframe.index)).replace(0, np.nan).fillna(1.0)
        )
        termo_dataframe["weight_sampling"] = 1.0 / termo_dataframe["prob"]

        feature_columns = list(final_calibration.keys())
        for column in feature_columns:
            if column not in termo_dataframe.columns:
                termo_dataframe[column] = 0.0

        bounds = None
        if (
            self.raking_bounds_termo
            and isinstance(self.raking_bounds_termo, (list, tuple))
            and len(self.raking_bounds_termo) == 2
        ):
            bounds = (
                float(self.raking_bounds_termo[0]),
                float(self.raking_bounds_termo[1]),
            )

        termo_dataframe["calib_weight_B"] = raking_calibration(
            dataframe=termo_dataframe,
            base_weight_column="weight_sampling",
            feature_columns=feature_columns,
            targets=final_calibration,
            max_iterations=100_000,
            bounds=bounds,
        )

        logging.info(
            "Calibration of thermo B – weights: min=%.6f, q1=%.6f, med=%.6f, q3=%.6f, max=%.6f",
            float(termo_dataframe["calib_weight_B"].min()),
            float(termo_dataframe["calib_weight_B"].quantile(0.25)),
            float(termo_dataframe["calib_weight_B"].median()),
            float(termo_dataframe["calib_weight_B"].quantile(0.75)),
            float(termo_dataframe["calib_weight_B"].max()),
        )

        strata_values = termo_dataframe["strata_avg"].unique()
        average_parameters = pd.DataFrame(
            {
                "Rodzaj_budynku": [z.split("-")[0] for z in strata_values],
                "centralne": [z.split("-")[1] if "-" in z else "" for z in strata_values],
                "avg_param": np.nan,
            }
        )

        for i, value in enumerate(strata_values):
            mask = termo_dataframe["strata_avg"] == value
            avg_value = survey_ratio_point(
                dataframe=termo_dataframe,
                numerator_mask=mask,
                denominator_mask=mask,
                numerator_value_column="yearly_heat_demand",
                denominator_value_column="latent_area",
                weight_column="calib_weight_B",
            )
            average_parameters.loc[i, "avg_param"] = avg_value

        domain_area = survey_weighted_sum_table(
            dataframe=termo_dataframe,
            value_column="latent_area",
            group_by=["zefir_termo", self.building_type_column],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "powierzchnia"})

        domain_heat = survey_weighted_sum_table(
            dataframe=termo_dataframe,
            value_column="yearly_heat_demand",
            group_by=["zefir_termo", self.building_type_column],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "yearly_heat_demand"})

        domain_cool = survey_weighted_sum_table(
            dataframe=termo_dataframe,
            value_column="yearly_cooling_demand",
            group_by=["zefir_termo", self.building_type_column],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "yearly_cooling_demand"})

        domain_heat_water = survey_weighted_sum_table(
            dataframe=termo_dataframe,
            value_column="yearly_heat_water_demand",
            group_by=["zefir_termo", self.building_type_column],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "yearly_heat_water_demand"})

        domain_pv_max = survey_weighted_sum_table(
            dataframe=termo_dataframe,
            value_column="max_nominal_power_pv",
            group_by=["zefir_termo", self.building_type_column],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "max_nominal_power_pv"})

        domain_pv_base = survey_weighted_sum_table(
            dataframe=termo_dataframe,
            value_column="base_nominal_power",
            group_by=["zefir_termo", self.building_type_column],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "base_nominal_power_pv"})

        combined = (
            domain_area.merge(
                domain_heat,
                on=["zefir_termo", self.building_type_column],
                how="left",
            )
            .merge(
                domain_cool,
                on=["zefir_termo", self.building_type_column],
                how="left",
            )
            .merge(
                domain_heat_water,
                on=["zefir_termo", self.building_type_column],
                how="left",
            )
            .merge(
                domain_pv_max,
                on=["zefir_termo", self.building_type_column],
                how="left",
            )
            .merge(
                domain_pv_base,
                on=["zefir_termo", self.building_type_column],
                how="left",
            )
        )
        combined["strata"] = combined[self.building_type_column].astype(str) + "_" + combined["zefir_termo"].astype(str)

        proportion_columns = [
            "boiler_new",
            "boiler_old",
            "Kocioł_gazowy",
            "Miejska_sieć_ciepłownicza",
            "Ogrzewanie_elektryczne",
            "Pompa_ciepła",
            "heat_connect",
            "heat_disconnect",
            "cwu_boiler_new",
            "cwu_boiler_old",
            "cwu_Kocioł_gazowy",
            "cwu_Miejska_sieć_ciepłownicza",
            "cwu_Ogrzewanie_elektryczne",
            "cwu_Pompa_ciepła",
        ]
        for column in proportion_columns:
            if column not in combined.columns:
                combined[column] = 0.0

        denominators = sorted(termo_dataframe["denominator"].unique())
        nominators = termo_dataframe["nominator"].unique()
        cwu_nominators = termo_dataframe["cwu_nominator"].unique()
        heat_nominators = termo_dataframe["heat_nominator"].unique()

        for denominator_key in denominators:
            nominators_for_den = [x for x in nominators if str(x).startswith(denominator_key + "_")]
            for nominator_key in nominators_for_den:
                column_temp = str(nominator_key).replace(denominator_key + "_", "")
                column_temp = translate_heat_source_column(column_temp)
                numerator_mask = termo_dataframe["nominator"].astype(str) == str(nominator_key)
                denominator_mask = termo_dataframe["denominator"].astype(str) == str(denominator_key)
                value = survey_ratio_point(
                    dataframe=termo_dataframe,
                    numerator_mask=numerator_mask,
                    denominator_mask=denominator_mask,
                    numerator_value_column="latent_area",
                    denominator_value_column="latent_area",
                    weight_column="calib_weight_B",
                )
                combined.loc[combined["strata"] == denominator_key, column_temp] = value

            heat_for_den = [x for x in heat_nominators if str(x).startswith(denominator_key + "_")]
            for heat_key in heat_for_den:
                temp = str(heat_key).replace(denominator_key + "_", "")
                output_column = "heat_connect" if temp in ("True", "1", "true", "TRUE") else "heat_disconnect"
                numerator_mask = termo_dataframe["heat_nominator"].astype(str) == str(heat_key)
                denominator_mask = termo_dataframe["denominator"].astype(str) == str(denominator_key)
                value = survey_ratio_point(
                    dataframe=termo_dataframe,
                    numerator_mask=numerator_mask,
                    denominator_mask=denominator_mask,
                    numerator_value_column="latent_area",
                    denominator_value_column="latent_area",
                    weight_column="calib_weight_B",
                )
                combined.loc[combined["strata"] == denominator_key, output_column] = value

            cwu_for_den = [x for x in cwu_nominators if str(x).startswith(denominator_key + "_")]
            for cwu_key in cwu_for_den:
                column_temp = str(cwu_key).replace(denominator_key + "_", "")
                temp_column = translate_heat_source_column(f"cwu_{column_temp}")
                numerator_mask = termo_dataframe["cwu_nominator"].astype(str) == str(cwu_key)
                denominator_mask = termo_dataframe["denominator"].astype(str) == str(denominator_key)
                value = survey_ratio_point(
                    dataframe=termo_dataframe,
                    numerator_mask=numerator_mask,
                    denominator_mask=denominator_mask,
                    numerator_value_column="latent_area",
                    denominator_value_column="latent_area",
                    weight_column="calib_weight_B",
                )
                combined.loc[combined["strata"] == denominator_key, temp_column] = value

        combined = combined.fillna(0.0)

        self.termo_calibrated_B = termo_dataframe
        self.avg_params_B = average_parameters
        return combined, average_parameters


# ---------------------------
# Runner
# ---------------------------


def run_estimation_b(
    engine: Engine,
    config: PostprocessingConfig,
    global_values: pd.DataFrame,
) -> None:
    """
    Run full Estimation B workflow: load inputs, calibrate, aggregate results,
    and save outputs to database.

    Args:
        config : PostprocessingConfig instance.
        global_values : DataFrame with global values.

    Returns:
        Final domain-level B estimation results.
    """
    if global_values.empty:
        raise ValueError("EstimationB.load_inputs: global_values dataframe is empty.")

    estimation = EstimationB(engine, config, global_values)
    estimation.load_inputs()
    estimation.compute_latent_area()
    estimation.build_global_calibration_vectors()
    estimation.calibrate_operat_and_build_super_global()
    result, avg_params = estimation.final_estimation()

    save_dataframe_to_db(estimation.engine, result, "protostrefy_b")
    save_dataframe_to_db(estimation.engine, avg_params, "avg_params_b")

    logging.info("B: Saved results to database.")
    logging.info("End of Estimation B.")
