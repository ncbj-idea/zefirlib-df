from __future__ import annotations

import logging
import textwrap

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine
from statsmodels.genmod import families
from statsmodels.genmod.generalized_linear_model import GLM
from statsmodels.tools import add_constant

from datafusion.configs.postprocessing_config import PostprocessingConfig
from datafusion.postprocessing.helpers.helpers_estimations import (
    h3_get_parent,
    pps_systematic,
    raking_calibration,
    read_estimations_inputs,
    survey_ratio_jackknife,
    survey_ratio_point,
    survey_weighted_sum_table,
    translate_heat_source_column,
)
from datafusion.utils.crud import save_dataframe_to_db
from datafusion.utils.validation import require_columns

# ---------------------------
# Estimation_A
# ---------------------------


class EstimationA:
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
        self.general_function_column = columns_config.funk_ogolna
        self.h3_sampling_column = columns_config.h3
        self.h3_estimation_column = columns_config.h3_estimation or self.h3_sampling_column

        params_config = config.params
        self.gus_factor = float(params_config.gus_factor)
        self.hex_size = float(params_config.hex_size)
        self.heat_strat_column = params_config.heat_strat
        self.pv_power = float(params_config.pv_power)
        self.mieszkalne_pv = float(params_config.mieszkalne_pv or params_config.mieszkalne_r or 0.0)

        self.seed_h3 = int(params_config.seed_h3)
        self.seed_lasso = int(params_config.seed_lass or params_config.seed_lasso or 123)
        self.seed_operat = int(params_config.seed_open or params_config.seed_operat or 789)
        self.seed_termo = int(params_config.seed_term or params_config.seed_termo or 542)

        self.raking_bounds_operat = (
            params_config.raking_bounds_operat_a
            if params_config.raking_bounds_operat_a is not None
            else params_config.raking_bounds_operat_b
        )
        self.raking_bounds_termo = (
            params_config.raking_bounds_termo_a
            if params_config.raking_bounds_termo_a is not None
            else params_config.raking_bounds_termo_b
        )

        self.pps_method = str(params_config.pps_method).lower()

        self.calibrate_area = bool(params_config.calib_area)
        self.calibrate_heat = bool(params_config.calib_heat)
        self.calibrate_gas = bool(params_config.calib_gas)
        self.calibrate_age = bool(params_config.calib_wiek or params_config.calib_wiel or False)

        self.living_building_types = ("jednorodzinny", "wielorodzinny", "kamienica")

        self.calibration_operat: dict[str, float] = {}
        self.calibration_termo: dict[str, float] = {}

    # ───────── Read inputs ─────────

    def load_inputs(
        self,
    ) -> None:
        """Loads inputs."""
        data = read_estimations_inputs(self.engine)

        self.operat_raw = data["operat"].copy()
        self.termo_raw = data["estimation"].copy()

        if self.operat_raw.empty:
            raise ValueError("load_inputs: operat_raw is empty.")

        if "h3_8" in self.operat_raw.columns:
            try:
                target_resolution = (
                    int(str(self.h3_estimation_column).split("_")[-1]) if "h3_" in self.h3_estimation_column else 7
                )
            except Exception:
                target_resolution = 7
            self.operat_raw["h3_8"] = (
                self.operat_raw["h3_8"].astype(str).map(lambda x: h3_get_parent(x, target_resolution))
            )

    # ───────── Latent_area ─────────

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
            [self.weight_column, self.usable_area_column, self.building_type_column],
            context="compute_latent_area – operat",
        )
        if not termo_dataframe.empty:
            require_columns(
                termo_dataframe,
                [self.usable_area_column, self.building_type_column],
                context="compute_latent_area – termo",
            )

        operat_dataframe[self.weight_column] = operat_dataframe[self.weight_column].fillna(1.0)

        operat_dataframe = operat_dataframe[
            operat_dataframe[self.building_type_column].isin(self.living_building_types)
        ].copy()
        termo_dataframe = termo_dataframe[
            termo_dataframe[self.building_type_column].isin(self.living_building_types)
        ].copy()

        if operat_dataframe.empty:
            raise ValueError("compute_latent_area: no rows in operat after filtering to living_building_types.")

        ratio_column = "wspolczynnik_powierzchni_uzytkowej_do_powierzchni_zabudowy"
        for dataframe in (operat_dataframe, termo_dataframe):
            if dataframe.empty:
                continue
            if ratio_column not in dataframe.columns:
                dataframe[ratio_column] = 1.0
            dataframe["latent_area"] = (
                dataframe[self.usable_area_column].astype(float)
                * float(self.gus_factor)
                * dataframe[self.weight_column].astype(float)
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

    # ───────── Vectors global configuration ─────────

    def build_global_calibration_vectors(self) -> None:
        """
        Build calibration targets and wide-format design variables for area, heat and
        gas based on global values and operat/termo data.
        """
        global_values_dataframe = self.global_values

        require_columns(
            global_values_dataframe,
            ["global_par", "global_value"],
            context="build_global_calibration_vectors – global_values",
        )

        if self.calibrate_age:
            mask = global_values_dataframe["global_par"].isin(
                ["stary", "po 1950r.", "po 1990r.", "Nowy po 2010r", "nieznany"]
            )
            building_age = global_values_dataframe.loc[mask, ["global_par", "global_value"]].copy()
            self.calibration_termo.update(
                pd.Series(
                    building_age["global_value"].to_numpy(),
                    index=building_age["global_par"].astype(str),
                ).to_dict()
            )
            age_column = "Wiek_budynku_p_modern"
            if age_column in self.termo.columns:
                termo_dataframe = self.termo.copy()
                termo_dataframe["latent_area2"] = termo_dataframe["latent_area"]
                wide_age = termo_dataframe.pivot_table(
                    index=termo_dataframe.index,
                    columns=age_column,
                    values="latent_area2",
                    aggfunc="sum",
                    fill_value=0,
                )
                self.termo = pd.concat([termo_dataframe.drop(columns=["latent_area2"]), wide_age], axis=1)

        if self.calibrate_area:
            indicator = global_values_dataframe["global_par"].astype(str).str.contains(
                "_871"
            ) & global_values_dataframe["global_par"].astype(str).str.contains("jednorodzinny|wielorodzinny|kamienica")
            hex_dataframe = global_values_dataframe.loc[indicator, ["global_par", "global_value"]].copy()

            def _strata_from_parameter(parameter: str) -> str:
                if "jednorodzinny" in parameter:
                    return "jednorodzinny"
                if "wielorodzinny" in parameter:
                    return "wielorodzinny"
                return "kamienica"

            hex_dataframe["strata"] = hex_dataframe["global_par"].map(_strata_from_parameter)

            chosen_indices: list[int] = []
            rng = np.random.default_rng(self.seed_h3)
            for _, group in hex_dataframe.groupby("strata", observed=True, dropna=False):
                group_size = max(1, int(np.floor(len(group) * self.hex_size)))
                sizes = group["global_value"].to_numpy(dtype=float)
                mask = pps_systematic(sizes, n=group_size, rng=rng)
                chosen_indices.extend(group.index[mask].tolist())

            chosen_hex = hex_dataframe.loc[chosen_indices]
            logging.info(
                "PPS systematic selection picked %d/%d hexes (hex_size=%.2f).",
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
                    "columns.h3_estimation not found – using columns.h3 = '%s'.",
                    h3_column,
                )
            else:
                h3_column = None
                logging.warning(
                    "Missing H3 column (neither '%s' nor '%s'). Skipping pivot on H3.",
                    self.h3_estimation_column,
                    self.h3_sampling_column,
                )

            if h3_column is not None:
                temp_key = self.operat[self.building_type_column].astype(str) + "_" + self.operat[h3_column].astype(str)
                operat_dataframe = self.operat.copy()
                operat_dataframe["latent_area2"] = operat_dataframe["latent_area"]
                wide_operat = pd.pivot_table(
                    operat_dataframe.assign(temp_ll=temp_key),
                    index=operat_dataframe.index,
                    columns="temp_ll",
                    values="latent_area2",
                    aggfunc="sum",
                    fill_value=0,
                )
                self.operat = pd.concat(
                    [operat_dataframe.drop(columns=["latent_area2"]), wide_operat],
                    axis=1,
                )

        if self.calibrate_heat:
            mask = global_values_dataframe["global_par"].astype(str).str.contains(
                r"heat_.+_area"
            ) & global_values_dataframe["global_par"].astype(str).str.contains("jednorodzinny|wielorodzinny")
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
                fill_value=0,
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
                    fill_value=0,
                )
                self.termo = pd.concat([termo_dataframe.drop(columns=["latent_area2"]), wide_termo], axis=1)

        if self.calibrate_gas:
            mask = global_values_dataframe["global_par"].astype(str).str.contains(
                r"gas_.+_area"
            ) & global_values_dataframe["global_par"].astype(str).str.contains("jednorodzinny|wielorodzinny")
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
                fill_value=0,
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
                    fill_value=0,
                )
                self.termo = pd.concat([termo_dataframe.drop(columns=["latent_area2"]), wide_termo], axis=1)

    # ───────── Propensity (logit) ─────────

    def estimate_propensity(self) -> None:
        operat_dataframe = self.operat.copy()

        require_columns(
            operat_dataframe,
            [self.central_heating_column],
            context="estimate_propensity – operat",
        )

        operat_dataframe["in_sample"] = (~operat_dataframe[self.central_heating_column].isna()).astype(int)

        if operat_dataframe["in_sample"].sum() == 0:
            raise ValueError("estimate_propensity: no rows with non-NA central heating info.")

        predictors = pd.DataFrame(index=operat_dataframe.index)
        for col in ["gas_connected", "heat_connected"]:
            predictors[col] = operat_dataframe[col].astype(int) if col in operat_dataframe.columns else 0
        if self.general_function_column in operat_dataframe.columns:
            dummies = pd.get_dummies(
                operat_dataframe[self.general_function_column].astype(str),
                prefix=self.general_function_column,
                dtype=float,
            )
            predictors = pd.concat([predictors, dummies], axis=1)

        response = operat_dataframe["in_sample"].astype(int)
        predictors_const = add_constant(predictors, has_constant="add")

        model = GLM(response, predictors_const, family=families.Binomial())
        result = model.fit()
        predicted_probabilities = result.predict(predictors_const).clip(1e-6, 1 - 1e-6)

        operat_dataframe["non_random_prob"] = predicted_probabilities
        operat_dataframe["non_random_weight"] = 1.0 / predicted_probabilities

        self.operat = operat_dataframe
        self._logit_model_ = result

        try:
            summary_text = self._logit_model_.summary().as_text()
        except Exception:
            summary_text = str(self._logit_model_.summary())
        logging.info("Logit model – summary:\n%s", textwrap.indent(summary_text, "  "))

        logging.info(
            "Propensity: min=%.6f, q1=%.6f, med=%.6f, q3=%.6f, max=%.6f",
            float(operat_dataframe["non_random_prob"].min()),
            float(operat_dataframe["non_random_prob"].quantile(0.25)),
            float(operat_dataframe["non_random_prob"].median()),
            float(operat_dataframe["non_random_prob"].quantile(0.75)),
            float(operat_dataframe["non_random_prob"].max()),
        )
        logging.info(
            "Weights 1/p: min=%.6f, q1=%.6f, med=%.6f, q3=%.6f, max=%.6f",
            float((1 / operat_dataframe["non_random_prob"]).min()),
            float((1 / operat_dataframe["non_random_prob"]).quantile(0.25)),
            float((1 / operat_dataframe["non_random_prob"]).median()),
            float((1 / operat_dataframe["non_random_prob"]).quantile(0.75)),
            float((1 / operat_dataframe["non_random_prob"]).max()),
        )

    def build_initial_heat_structure(self) -> None:
        """
        Heated area structure by building type and heat source (BEFORE weight calibration),
        calculated on a sample with ‘central’ propensity weights.
        Creates:
        - self.initial_heat_structure_long
        - self.initial_heat_structure_wide and saves the histogram of shares.
        """
        sample_dataframe = self.operat.loc[~self.operat[self.central_heating_column].isna()].copy()

        if sample_dataframe.empty:
            logging.warning("No records from the central database != NA – omitting the initial structure.")
            self.initial_heat_structure_long = pd.DataFrame()
            self.initial_heat_structure_wide = pd.DataFrame()
            return

        require_columns(
            sample_dataframe,
            [self.building_type_column, self.central_heating_column, "latent_area"],
            context="build_initial_heat_structure – sample",
        )

        sample_dataframe[self.building_type_column] = sample_dataframe[self.building_type_column].astype(str)
        sample_dataframe[self.central_heating_column] = sample_dataframe[self.central_heating_column].astype(str)
        sample_dataframe["latent_area_use"] = sample_dataframe["latent_area"].astype(float)
        weight_column = "non_random_weight"
        if weight_column not in sample_dataframe.columns:
            logging.warning("The non_random_weight column is missing – assuming weights = 1.0.")
            sample_dataframe[weight_column] = 1.0

        heat_structure_long = (
            sample_dataframe.groupby(
                [self.building_type_column, self.central_heating_column],
                observed=True,
                dropna=False,
            )
            .apply(lambda d: np.sum(d["latent_area_use"] * d[weight_column]))
            .rename("area")
            .reset_index()
        )

        heat_structure_long["area"] = heat_structure_long["area"].astype(float)
        by_building_type = heat_structure_long.groupby(self.building_type_column, observed=True, dropna=False)[
            "area"
        ].transform("sum")
        heat_structure_long["share_pct"] = np.where(
            by_building_type > 0,
            100.0 * heat_structure_long["area"] / by_building_type,
            0.0,
        )

        heat_structure_wide = heat_structure_long.pivot_table(
            index=self.building_type_column,
            columns=self.central_heating_column,
            values="share_pct",
            aggfunc="first",
            fill_value=0.0,
            observed=True,
        ).reset_index()

        self.initial_heat_structure_long = heat_structure_long.sort_values(
            [self.building_type_column, "area"],
            ascending=[True, False],
        ).reset_index(drop=True)
        self.initial_heat_structure_wide = heat_structure_wide

        logging.info(
            "Structure (pre-calibration) – TOP 10 rows:\n%s",
            self.initial_heat_structure_long.head(10).to_string(index=False),
        )

    # ───────── Calibration A (operat) ─────────

    def calibrate_operat_and_build_super_global(self) -> None:
        """
        Calibrate operat weights by raking and build super-global central-heating
        area totals.
        """
        sample_dataframe = self.operat.loc[~self.operat[self.central_heating_column].isna()].copy()

        if sample_dataframe.empty:
            raise ValueError("calibrate_operat_and_build_super_global: no rows with central heating info.")

        require_columns(
            sample_dataframe,
            [
                "latent_area",
                "non_random_weight",
                self.building_type_column,
                self.central_heating_column,
            ],
            context="calibrate_operat_and_build_super_global – sample",
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

        sample_dataframe["calib_weight_A"] = raking_calibration(
            dataframe=sample_dataframe,
            base_weight_column="non_random_weight",
            feature_columns=feature_columns,
            targets=self.calibration_operat,
            max_iterations=10_000,
            bounds=bounds,
        )

        logging.info(
            "Calibration A – weights: min=%.6f, q1=%.6f, med=%.6f, q3=%.6f, max=%.6f",
            float(sample_dataframe["calib_weight_A"].min()),
            float(sample_dataframe["calib_weight_A"].quantile(0.25)),
            float(sample_dataframe["calib_weight_A"].median()),
            float(sample_dataframe["calib_weight_A"].quantile(0.75)),
            float(sample_dataframe["calib_weight_A"].max()),
        )

        central_heating_area = survey_weighted_sum_table(
            dataframe=sample_dataframe.assign(_latent=sample_dataframe["latent_area"]),
            value_column="_latent",
            group_by=[self.building_type_column, self.central_heating_column],
            weight_column="calib_weight_A",
        )
        if not central_heating_area.empty:
            central_heating_area["calib_par"] = (
                "centralne_"
                + central_heating_area[self.building_type_column].astype(str)
                + "_"
                + central_heating_area[self.central_heating_column].astype(str).str.replace(" ", "_", regex=False)
            )
            super_global = central_heating_area.loc[central_heating_area["Freq"] != 0, ["calib_par", "Freq"]].copy()
        else:
            super_global = pd.DataFrame({"calib_par": [], "Freq": []})

        self.super_global = super_global

    # ───────── Final calibration and estimation ─────────

    def final_estimation(self) -> pd.DataFrame:
        """
        Perform final A-estimation: calibrate thermo sample, derive energy and PV
        indicators, and aggregate domain-level results.
        """
        termo_dataframe = self.termo.copy()

        if termo_dataframe.empty:
            raise ValueError("final_estimation: termo dataframe is empty.")

        require_columns(
            termo_dataframe,
            [
                "Klasa_termo",
                "latent_area",
                self.building_type_column,
                self.central_heating_column,
                self.hot_water_column,
                self.footprint_area_column,
                self.weight_column,
            ],
            context="final_estimation – termo",
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

        for new_column, source_column in [
            ("yearly_heat_demand", "heat"),
            ("yearly_heat_water_demand", "heat_water"),
            ("yearly_cooling_demand", "cold"),
        ]:
            termo_dataframe[new_column] = (
                termo_dataframe["latent_area"] * termo_dataframe.get(source_column, 0.0)
            ).fillna(0.0)

        final_calibration = pd.Series(
            self.super_global["Freq"].to_numpy(),
            index=self.super_global["calib_par"].astype(str),
        ).to_dict()
        final_calibration.update(self.calibration_termo)
        final_calibration = {key.replace(" ", "_"): float(value) for key, value in final_calibration.items()}

        termo_dataframe["rodzaj_budynku2"] = np.where(
            termo_dataframe[self.building_type_column] != "kamienica",
            termo_dataframe[self.building_type_column],
            np.where(
                termo_dataframe.get("funkcja_szczegolowa_budynku", "") == "budynek jednorodzinny",
                "jednorodzinny",
                "wielorodzinny",
            ),
        )

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
                fill_value=0,
            )
            termo_dataframe = pd.concat([termo_dataframe, wide], axis=1)

        termo_dataframe["nominator"] = (
            termo_dataframe["rodzaj_budynku2"].astype(str)
            + "_"
            + termo_dataframe["zefir_termo"].astype(str)
            + "_"
            + termo_dataframe[self.central_heating_column].astype(str).str.replace(" ", "_", regex=False)
        )
        termo_dataframe["cwu_nominator"] = (
            termo_dataframe["rodzaj_budynku2"].astype(str)
            + "_"
            + termo_dataframe["zefir_termo"].astype(str)
            + "_"
            + termo_dataframe[self.hot_water_column].astype(str).str.replace(" ", "_", regex=False)
        )
        if self.heat_strat_column not in termo_dataframe.columns:
            termo_dataframe[self.heat_strat_column] = ""
        termo_dataframe["heat_nominator"] = (
            termo_dataframe["rodzaj_budynku2"].astype(str)
            + "_"
            + termo_dataframe["zefir_termo"].astype(str)
            + "_"
            + termo_dataframe[self.heat_strat_column].astype(str)
        )
        termo_dataframe["denominator"] = (
            termo_dataframe["rodzaj_budynku2"].astype(str) + "_" + termo_dataframe["zefir_termo"].astype(str)
        )

        termo_dataframe["max_nominal_power_pv"] = (
            termo_dataframe[self.weight_column]
            * termo_dataframe[self.footprint_area_column]
            * 0.5
            * float(self.pv_power)
        )
        termo_dataframe["base_nominal_power"] = (
            np.where(termo_dataframe["rodzaj_budynku2"] == "jednorodzinny", 0.9, 0.1)
            * termo_dataframe[self.weight_column]
            * termo_dataframe[self.footprint_area_column]
            * float(self.mieszkalne_pv)
        )
        termo_dataframe["strata_avg"] = (
            termo_dataframe["rodzaj_budynku2"].astype(str) + "-" + termo_dataframe["zefir_termo"].astype(str)
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
            max_iterations=10_000,
            bounds=bounds,
        )

        logging.info(
            "Calibration B – weights: min=%.6f, q1=%.6f, med=%.6f, q3=%.6f, max=%.6f",
            float(termo_dataframe["calib_weight_B"].min()),
            float(termo_dataframe["calib_weight_B"].quantile(0.25)),
            float(termo_dataframe["calib_weight_B"].median()),
            float(termo_dataframe["calib_weight_B"].quantile(0.75)),
            float(termo_dataframe["calib_weight_B"].max()),
        )

        ratio_psu_column = self.h3_estimation_column if self.h3_estimation_column in termo_dataframe.columns else None

        def _recalibrate_replica(replica_dataframe: pd.DataFrame) -> pd.Series:
            feature_columns_local = list(final_calibration.keys())
            for column in feature_columns_local:
                if column not in replica_dataframe.columns:
                    replica_dataframe[column] = 0.0

            bounds_local = None
            if (
                self.raking_bounds_termo
                and isinstance(self.raking_bounds_termo, (list, tuple))
                and len(self.raking_bounds_termo) == 2
            ):
                bounds_local = (
                    float(self.raking_bounds_termo[0]),
                    float(self.raking_bounds_termo[1]),
                )

            replica_weights = raking_calibration(
                dataframe=replica_dataframe,
                base_weight_column="weight_sampling",
                feature_columns=feature_columns_local,
                targets=final_calibration,
                max_iterations=10_000,
                bounds=bounds_local,
            )
            replica_weights.name = "calib_weight_B"
            return replica_weights

        domain_area = survey_weighted_sum_table(
            termo_dataframe,
            "latent_area",
            group_by=["zefir_termo", "rodzaj_budynku2"],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "powierzchnia"})
        domain_heat = survey_weighted_sum_table(
            termo_dataframe,
            "yearly_heat_demand",
            group_by=["zefir_termo", "rodzaj_budynku2"],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "yearly_heat_demand"})
        domain_cool = survey_weighted_sum_table(
            termo_dataframe,
            "yearly_cooling_demand",
            group_by=["zefir_termo", "rodzaj_budynku2"],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "yearly_cooling_demand"})
        domain_heat_water = survey_weighted_sum_table(
            termo_dataframe,
            "yearly_heat_water_demand",
            group_by=["zefir_termo", "rodzaj_budynku2"],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "yearly_heat_water_demand"})
        domain_pv_max = survey_weighted_sum_table(
            termo_dataframe,
            "max_nominal_power_pv",
            group_by=["zefir_termo", "rodzaj_budynku2"],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "max_nominal_power_pv"})
        domain_pv_base = survey_weighted_sum_table(
            termo_dataframe,
            "base_nominal_power",
            group_by=["zefir_termo", "rodzaj_budynku2"],
            weight_column="calib_weight_B",
        ).rename(columns={"Freq": "base_nominal_power_pv"})

        combined_dataframe = (
            domain_area.merge(domain_heat, on=["zefir_termo", "rodzaj_budynku2"], how="left")
            .merge(domain_cool, on=["zefir_termo", "rodzaj_budynku2"], how="left")
            .merge(domain_heat_water, on=["zefir_termo", "rodzaj_budynku2"], how="left")
            .merge(domain_pv_max, on=["zefir_termo", "rodzaj_budynku2"], how="left")
            .merge(domain_pv_base, on=["zefir_termo", "rodzaj_budynku2"], how="left")
        )
        combined_dataframe["strata"] = (
            combined_dataframe["rodzaj_budynku2"].astype(str) + "_" + combined_dataframe["zefir_termo"].astype(str)
        )

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
            if column not in combined_dataframe.columns:
                combined_dataframe[column] = 0.0

        denominators = sorted(termo_dataframe["denominator"].unique())
        nominators = termo_dataframe["nominator"].unique()
        cwu_nominators = termo_dataframe["cwu_nominator"].unique()
        heat_nominators = termo_dataframe["heat_nominator"].unique()

        for denominator_key in denominators:
            matching_nominators = [j for j in nominators if str(j).startswith(denominator_key + "_")]
            for nominator_key in matching_nominators:
                column_name = str(nominator_key).replace(denominator_key + "_", "")
                column_name = translate_heat_source_column(column_name)
                numerator_mask = termo_dataframe["nominator"].astype(str) == str(nominator_key)
                denominator_mask = termo_dataframe["denominator"].astype(str) == str(denominator_key)

                theta_point = survey_ratio_point(
                    dataframe=termo_dataframe,
                    numerator_mask=numerator_mask,
                    denominator_mask=denominator_mask,
                    numerator_value_column="latent_area",
                    denominator_value_column="latent_area",
                    weight_column="calib_weight_B",
                )
                theta_jk, se_jk = survey_ratio_jackknife(
                    dataframe=termo_dataframe,
                    numerator_mask=numerator_mask,
                    denominator_mask=denominator_mask,
                    numerator_value_column="latent_area",
                    denominator_value_column="latent_area",
                    weight_column="calib_weight_B",
                    cluster_column=ratio_psu_column,
                    recalibrate_function=_recalibrate_replica,
                )
                combined_dataframe.loc[combined_dataframe["strata"] == denominator_key, column_name] = theta_point
                combined_dataframe.loc[
                    combined_dataframe["strata"] == denominator_key,
                    f"{column_name}_jk",
                ] = theta_jk
                combined_dataframe.loc[
                    combined_dataframe["strata"] == denominator_key,
                    f"{column_name}_jk_se",
                ] = se_jk

            matching_heat_nominators = [k for k in heat_nominators if str(k).startswith(denominator_key + "_")]
            for heat_key in matching_heat_nominators:
                temp_column = str(heat_key).replace(denominator_key + "_", "")
                output_column = "heat_connect" if (temp_column in ("True", "1", "true", "TRUE")) else "heat_disconnect"
                numerator_mask = termo_dataframe["heat_nominator"].astype(str) == str(heat_key)
                denominator_mask = termo_dataframe["denominator"].astype(str) == str(denominator_key)

                theta_point = survey_ratio_point(
                    dataframe=termo_dataframe,
                    numerator_mask=numerator_mask,
                    denominator_mask=denominator_mask,
                    numerator_value_column="latent_area",
                    denominator_value_column="latent_area",
                    weight_column="calib_weight_B",
                )
                theta_jk, se_jk = survey_ratio_jackknife(
                    dataframe=termo_dataframe,
                    numerator_mask=numerator_mask,
                    denominator_mask=denominator_mask,
                    numerator_value_column="latent_area",
                    denominator_value_column="latent_area",
                    weight_column="calib_weight_B",
                    cluster_column=ratio_psu_column,
                    recalibrate_function=_recalibrate_replica,
                )
                combined_dataframe.loc[combined_dataframe["strata"] == denominator_key, output_column] = theta_point
                combined_dataframe.loc[
                    combined_dataframe["strata"] == denominator_key,
                    f"{output_column}_jk",
                ] = theta_jk
                combined_dataframe.loc[
                    combined_dataframe["strata"] == denominator_key,
                    f"{output_column}_jk_se",
                ] = se_jk

            matching_cwu_nominators = [j for j in cwu_nominators if str(j).startswith(denominator_key + "_")]
            for cwu_key in matching_cwu_nominators:
                column_name_base = str(cwu_key).replace(denominator_key + "_", "")
                temp_column_name = translate_heat_source_column(f"cwu_{column_name_base}")
                numerator_mask = termo_dataframe["cwu_nominator"].astype(str) == str(cwu_key)
                denominator_mask = termo_dataframe["denominator"].astype(str) == str(denominator_key)

                theta_point = survey_ratio_point(
                    dataframe=termo_dataframe,
                    numerator_mask=numerator_mask,
                    denominator_mask=denominator_mask,
                    numerator_value_column="latent_area",
                    denominator_value_column="latent_area",
                    weight_column="calib_weight_B",
                )
                theta_jk, se_jk = survey_ratio_jackknife(
                    dataframe=termo_dataframe,
                    numerator_mask=numerator_mask,
                    denominator_mask=denominator_mask,
                    numerator_value_column="latent_area",
                    denominator_value_column="latent_area",
                    weight_column="calib_weight_B",
                    cluster_column=ratio_psu_column,
                    recalibrate_function=_recalibrate_replica,
                )
                combined_dataframe.loc[combined_dataframe["strata"] == denominator_key, temp_column_name] = theta_point
                combined_dataframe.loc[
                    combined_dataframe["strata"] == denominator_key,
                    f"{temp_column_name}_jk",
                ] = theta_jk
                combined_dataframe.loc[
                    combined_dataframe["strata"] == denominator_key,
                    f"{temp_column_name}_jk_se",
                ] = se_jk

        combined_dataframe = combined_dataframe.fillna(0.0)

        self.termo_calibrated = termo_dataframe
        return combined_dataframe


# ---------------------------
# Runner
# ---------------------------


def run_estimation_a(
    engine: Engine,
    config: PostprocessingConfig,
    global_values: pd.DataFrame,
) -> None:
    """
    Run full Estimation A workflow: load inputs, calibrate, aggregate results,
    and save outputs to Excel/CSV.

    Args:
        config : PostprocessingConfig instance.
        global_values : DataFrame with global values.

    Returns:
        Final domain-level A estimation results.
    """

    if global_values.empty:
        raise ValueError("run_estimation_a: global_values is empty.")

    estimation = EstimationA(engine, config, global_values)
    estimation.load_inputs()
    estimation.compute_latent_area()
    estimation.build_global_calibration_vectors()
    estimation.estimate_propensity()
    estimation.build_initial_heat_structure()
    estimation.calibrate_operat_and_build_super_global()
    result = estimation.final_estimation()

    if "rodzaj_budynku2" in result.columns:
        result = result.rename(columns={"rodzaj_budynku2": "Rodzaj_budynku"})

    save_dataframe_to_db(estimation.engine, result, "protostrefy_a")

    if getattr(estimation, "initial_heat_structure_long", None) is not None:
        save_dataframe_to_db(
            estimation.engine,
            estimation.initial_heat_structure_long,
            "protostrefy_a_precalib_heat_structure_long",
        )

    if getattr(estimation, "initial_heat_structure_wide", None) is not None:
        save_dataframe_to_db(
            estimation.engine,
            estimation.initial_heat_structure_wide,
            "protostrefy_a_precalib_heat_structure_wide",
        )

    logging.info("Results saved to database.")
    logging.info("End of Estimation A.")
