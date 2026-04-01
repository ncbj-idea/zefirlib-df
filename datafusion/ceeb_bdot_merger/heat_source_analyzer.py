"""Heat source analyzer for building equipment data.

This module implements the HeatSourceAnalyzer class that processes merged CEEB and BDOT
data to determine weighted heat source pairs for each building.
"""

import logging
import math

import pandas as pd

from datafusion.configs.merge_config import HeatSourceAnalysisParams
from datafusion.constants import (
    COLUMN_CO_SOURCE,
    COLUMN_CWU_SOURCE,
    COLUMN_PAIR_WEIGHT,
)

from .heat_source_defaults import DEFAULT_FLOOR_AREA_RATIO
from .helpers import _to_bool_series, _validate_columns_exist

_logger = logging.getLogger(__name__)

# CEEB device-specific columns that should be excluded from building-level output
# These columns vary per heating device/declaration and are not building-level attributes.
# Building-level columns like typ_deklaracji, pow_obrysu_m2, pow_uzytkowa_m2, and id
# are preserved via BUILDING_LEVEL_COLUMNS constant (see below).
CEEB_DEVICE_SPECIFIC_COLUMNS = {
    "Źródło_ciepła",  # Heat source (varies per device)
    "C.O.",  # Central heating flag (varies per device)
    "C.W.U.",  # Hot water flag (varies per device)
    "heat_source_classified",  # Derived column (varies per device)
    "Ekoprojekt",  # Boiler class counts
    "Klasa_5",
    "Klasa_4",
    "Klasa_3",
    "Poniżej_klasy_3_lub_brak_informacji",
    "Liczba_eksploatowanych_źródeł_ciepła",  # Device counts
    "Liczba_zainstalowanych_źródeł_ciepła",
    "Numer_lokalu",  # Apartment/unit number (varies per declaration)
    "duplication_id",  # Processing artifact
    "ulica_mod",  # Processing artifact from address cleaning
    "bdot_key",  # Processing artifact from joining
    "ulica_sim",  # Processing artifact from similarity matching
    "id_ceeb",  # CEEB identifier (conflicts with BDOT id, renamed during merge)
}

# Building-level columns that should be preserved (excluded from device-specific filtering)
# These columns have consistent values across all declarations for a given building
BUILDING_LEVEL_COLUMNS = {
    "pow_obrysu_m2",  # Building footprint area
    "pow_uzytkowa_m2",  # Usable area
    "typ_deklaracji",  # Declaration type (A or B) - taken from first declaration per building
    "id",  # Building identifier
}


class HeatSourceAnalyzer:
    """Analyzer for determining building heat source pairs and their weights."""

    def __init__(self, config: HeatSourceAnalysisParams):
        """Initialize HeatSourceAnalyzer with configuration.

        Args:
            config: Configuration dictionary (typically from HeatSourceAnalysisParams Pydantic model)
                with the following keys:
                - source_translation: Mapping of source names to internal names
                - central_hierarchy: Hierarchy for central heating sources
                - cwu_hierarchy: Hierarchy for domestic hot water sources
                - final_mapping: Mapping to canonical names
                - avg_apartment_area: Average apartment area in m2
                - gus_multiplicator: GUS multiplicator for apartment estimation
                - min_source_proportion: Minimum source proportion threshold
                - trash_threshold: Threshold for removing junk pairs
        """
        self.config = config

        # Use values directly from config (defaults handled by Pydantic model)
        self.source_translation = self.config.source_translation
        self.central_hierarchy = self.config.central_hierarchy
        self.cwu_hierarchy = self.config.cwu_hierarchy
        self.final_mapping = self.config.final_mapping
        self.avg_apartment_area = float(self.config.avg_apartment_area)
        self.gus_multiplicator = float(self.config.gus_multiplicator)
        self.floor_area_ratio_column = self.config.floor_area_ratio_column
        self.min_source_proportion = self.config.min_source_proportion
        self.trash_threshold = self.config.trash_threshold
        self.multifamily_building_type = self.config.multifamily_building_type
        self.single_family_max_heat_sources = self.config.single_family_max_heat_sources
        self.min_apartment_count = self.config.min_apartment_count
        self.max_weight = self.config.max_weight
        self.solid_fuel_auto = self.config.solid_fuel_auto
        self.solid_fuel_manual = self.config.solid_fuel_manual
        self.boiler_new = self.config.boiler_new
        self.boiler_old = self.config.boiler_old

    def run(self, merged_df: pd.DataFrame) -> pd.DataFrame:
        """Process merged data to generate weighted heat source pairs with building metadata.

        Args:
            merged_df: DataFrame from MergeReader containing merged CEEB/BDOT data

        Returns:
            DataFrame with heat source pairs and all building-level attributes:
            - Heat source columns: merged_id, co_source, cwu_source, proportion
            - Analysis columns: n_apartments, max_heat_sources, building_type
            - Building metadata: All building-level columns from input (spatial data,
              classifications, connectivity info, etc.) excluding CEEB device-specific
              columns (heat source details, declarations, boiler classes)
        """
        _logger.info("Starting heat source analysis...")

        # Validate input data
        self._validate_columns_exist(merged_df)

        # Convert boolean columns
        merged_df = self._convert_boolean_columns(merged_df)

        # Normalize heat source names
        merged_df = self._normalize_heat_source_names(merged_df)

        # Handle unheated buildings
        merged_df = self._ensure_at_least_one_heating_per_building(merged_df)

        # Assign solid fuel boiler classes based on priority (Assumption 8)
        # This replaces the simple classification with priority-based assignment
        merged_df = self._assign_classes_by_priority_per_building(merged_df)

        # Process per building to create weighted pairs
        # Note: We optimize to categorical AFTER processing to avoid fillna issues
        result_df = self._process_buildings(merged_df)

        # Convert all column names to lowercase
        result_df.columns = result_df.columns.str.lower()

        _logger.info("Heat source analysis completed.")
        return result_df

    def _validate_columns_exist(self, df: pd.DataFrame) -> None:
        """Validate that required columns exist in the DataFrame."""
        required_columns = [
            "merged_id",
            "Źródło_ciepła",  # Heat source
            "C.O.",  # Central heating
            "C.W.U.",  # Domestic hot water
            "Rodzaj_budynku_A",  # Building type
            "pow_uzytkowa_m2",  # Usable area
        ]
        _validate_columns_exist(df, required_columns, "merged data")

    def _convert_boolean_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert C.O. and C.W.U. columns to boolean."""
        df = df.copy()
        df["C.O."] = _to_bool_series(df["C.O."])
        df["C.W.U."] = _to_bool_series(df["C.W.U."])
        return df

    def _normalize_heat_source_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize heat source names using translation map."""
        df = df.copy()
        # Create a mapping series for translation
        translation_series = pd.Series(self.source_translation)
        # Map heat source names, keeping original if not in translation map
        df["heat_source_classified"] = df["Źródło_ciepła"].map(translation_series).fillna(df["Źródło_ciepła"])
        return df

    def _ensure_at_least_one_heating_per_building(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure at least one heating source per building (Assumption 6)."""
        df = df.copy()

        # Vectorized approach - more efficient and safer
        building_has_no_heating = df.groupby("merged_id").apply(lambda g: (~g["C.O."]).all() & (~g["C.W.U."]).all())
        buildings_to_fix = building_has_no_heating[building_has_no_heating].index

        mask = df["merged_id"].isin(buildings_to_fix)
        df.loc[mask, ["C.O.", "C.W.U."]] = True

        return df

    def _assign_classes_by_priority_per_building(self, df: pd.DataFrame) -> pd.DataFrame:
        """Assign boiler classes to solid fuel devices per building based on priority.

        Implements Assumption 8: Best classes (Ekoprojekt > Class_5 > Class_4, etc.)
        are assigned to devices that heat the most, in priority order:
        - Priority 3: CO=True AND CWU=True (heats both)
        - Priority 2: CO=True only (central heating only)
        - Priority 1: CWU=True only (hot water only)

        Also implements Assumption 7: Devices without class info get default classification
        based on feeder type (automatic -> Class 4, manual -> Class 3, both -> boiler_old).

        Args:
            df: DataFrame with merged CEEB/BDOT data

        Returns:
            DataFrame with heat_source_classified updated per building
        """
        _logger.info("Assigning solid fuel boiler classes by priority per building...")

        # Group by building and process each separately
        grouped = df.groupby("merged_id")

        # Handle empty DataFrame case
        if len(grouped) == 0:
            _logger.warning("No buildings to process, returning original DataFrame.")
            return df

        classified_groups = []

        for _merged_id, group in grouped:
            classified_group = self._assign_classes_for_building(group)
            classified_groups.append(classified_group)

        # Handle case where no groups were processed
        if not classified_groups:
            _logger.warning("No classified groups produced, returning original DataFrame.")
            return df

        result = pd.concat(classified_groups, ignore_index=True)
        _logger.info("Class assignment completed.")
        return result

    def _assign_classes_for_building(self, building_df: pd.DataFrame) -> pd.DataFrame:
        """Assign boiler classes for a single building's solid fuel devices.

        Args:
            building_df: DataFrame for a single building (one merged_id)

        Returns:
            DataFrame with updated heat_source_classified column
        """
        building_df = building_df.copy()

        # Filter to solid fuel boilers only
        solid_fuel_mask = building_df["heat_source_classified"].isin([self.solid_fuel_auto, self.solid_fuel_manual])

        if not solid_fuel_mask.any():
            # No solid fuel boilers in this building
            return building_df

        sf_devices = building_df[solid_fuel_mask].copy()
        sf_devices["_original_index"] = sf_devices.index

        # Calculate heating priority (Assumption 8)
        # Priority 3: Both CO and CWU
        # Priority 2: CO only
        # Priority 1: CWU only
        sf_devices["_priority"] = 0
        co_true = sf_devices["C.O."]
        cwu_true = sf_devices["C.W.U."]

        sf_devices.loc[co_true & cwu_true, "_priority"] = 3
        sf_devices.loc[co_true & ~cwu_true, "_priority"] = 2
        sf_devices.loc[~co_true & cwu_true, "_priority"] = 1

        # Sort by priority (descending) - highest priority gets best class
        sf_devices = sf_devices.sort_values("_priority", ascending=False).reset_index(drop=True)

        # Extract class counts from the first row (all rows have same counts for this building)
        def safe_int(series, col_name, default=0):
            """Safely extract integer count from series."""
            if col_name not in series.columns:
                return default
            val = series[col_name].iloc[0]
            if pd.isna(val):
                return default
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        ekoprojekt_count = safe_int(sf_devices, "Ekoprojekt")
        klasa_5_count = safe_int(sf_devices, "Klasa_5")
        klasa_4_count = safe_int(sf_devices, "Klasa_4")
        klasa_3_count = safe_int(sf_devices, "Klasa_3")
        below_3_count = safe_int(sf_devices, "Poniżej_klasy_3_lub_brak_informacji")

        # Assign classes in order of quality (Assumption 8)
        assigned_classes = []
        idx = 0
        total_devices = len(sf_devices)

        # Assign Ekoprojekt (best quality) -> boiler_new
        for _ in range(min(ekoprojekt_count, total_devices - idx)):
            assigned_classes.append(self.boiler_new)
            idx += 1

        # Assign Class 5 -> boiler_new
        for _ in range(min(klasa_5_count, total_devices - idx)):
            assigned_classes.append(self.boiler_new)
            idx += 1

        # Assign Class 4 -> boiler_old
        for _ in range(min(klasa_4_count, total_devices - idx)):
            assigned_classes.append(self.boiler_old)
            idx += 1

        # Assign Class 3 -> boiler_old
        for _ in range(min(klasa_3_count, total_devices - idx)):
            assigned_classes.append(self.boiler_old)
            idx += 1

        # Assign Below Class 3 -> boiler_old
        for _ in range(min(below_3_count, total_devices - idx)):
            assigned_classes.append(self.boiler_old)
            idx += 1

        # Apply Assumption 7 to remaining devices (no class info)
        # Automatic feeder -> Class 4 -> boiler_old (FIX for Issue 1)
        # Manual feeder -> Class 3 -> boiler_old
        while idx < total_devices:
            # All remaining devices without class info become boiler_old
            # (automatic feeder is Class 4, manual is Class 3, both are boiler_old)
            assigned_classes.append(self.boiler_old)
            idx += 1

        # Apply assignments back to the solid fuel devices
        sf_devices["heat_source_classified"] = assigned_classes
        sf_devices.set_index("_original_index", inplace=True)
        sf_devices = sf_devices.sort_index()
        sf_devices.drop(columns=["_priority"], inplace=True)

        # Merge back with non-solid-fuel devices
        building_df.loc[sf_devices.index, "heat_source_classified"] = sf_devices["heat_source_classified"].values

        return building_df

    def _get_floor_area_ratio(self, group_df: pd.DataFrame) -> float:
        """Return the floor-to-footprint ratio for the provided building group."""
        ratio_col = self.floor_area_ratio_column
        if ratio_col not in group_df.columns:
            return DEFAULT_FLOOR_AREA_RATIO
        ratio_value = group_df[ratio_col].iloc[0]
        if pd.isna(ratio_value):
            return DEFAULT_FLOOR_AREA_RATIO
        try:
            return float(ratio_value)
        except (TypeError, ValueError):
            return DEFAULT_FLOOR_AREA_RATIO

    def _estimate_apartment_count(self, group_df: pd.DataFrame) -> int:
        """Estimate the number of apartments for this building group."""
        try:
            usable_area = float(group_df["pow_uzytkowa_m2"].iloc[0])
        except (TypeError, ValueError):
            usable_area = 0.0

        floor_ratio = self._get_floor_area_ratio(group_df)
        gus_ratio = self.gus_multiplicator or 1.0

        if self.avg_apartment_area <= 0 or usable_area <= 0:
            return self.min_apartment_count

        raw_apartments = usable_area * gus_ratio * max(floor_ratio, 0.0) / self.avg_apartment_area
        apartments = math.floor(raw_apartments) if raw_apartments >= 0 else 0
        return max(self.min_apartment_count, int(apartments))

    def _estimate_max_heat_sources(self, group_df: pd.DataFrame, apartment_count: int) -> int:
        """Estimate maximum number of heat sources per building."""
        building_type = group_df["Rodzaj_budynku_A"].iloc[0]

        if building_type != self.multifamily_building_type:  # Multi-family
            return self.single_family_max_heat_sources

        return max(self.min_apartment_count, apartment_count)

    def _select_weighted_sources(
        self,
        group_df: pd.DataFrame,
        max_sources: int,
        hierarchy: list[str],
        role_col: str,
    ) -> pd.DataFrame:
        """Select and weight primary heat sources based on hierarchy."""
        # Filter declarations for specific role (CO or CWU)
        role_df = group_df[group_df[role_col]].copy()

        if role_df.empty:
            return pd.DataFrame(columns=["heat_source_classified", "weight", "role"])

        # Compute proportions per heat_source_classified (count-weighted)
        source_counts = role_df["heat_source_classified"].value_counts()

        # Convert to DataFrame for easier manipulation
        source_df = source_counts.to_frame("count").reset_index()
        source_df.columns = ["heat_source_classified", "count"]

        # Calculate initial weights
        total_count = source_df["count"].sum()
        if total_count > 0:
            source_df["weight"] = source_df["count"] / total_count
        else:
            source_df["weight"] = 0.0

        # For multi-family, filter out sources below min_source_proportion
        building_type = group_df["Rodzaj_budynku_A"].iloc[0]
        if building_type == self.multifamily_building_type and len(source_df) > 1:
            source_df = source_df[source_df["weight"] >= self.min_source_proportion]

        # Renormalize weights if any were filtered out
        if not source_df.empty and source_df["weight"].sum() > 0:
            source_df["weight"] = source_df["weight"] / source_df["weight"].sum()

        # Sort according to hierarchy
        source_df["hierarchy_index"] = (
            source_df["heat_source_classified"]
            .map({source: i for i, source in enumerate(hierarchy)})
            .fillna(len(hierarchy))
        )  # Put unknown sources at the end

        source_df = source_df.sort_values("hierarchy_index")

        # Select top N where N == max_sources
        selected_sources = source_df.head(max_sources).copy()
        selected_sources["role"] = role_col

        return selected_sources[["heat_source_classified", "weight", "role"]]

    def _create_pairs_and_weights(self, co_df: pd.DataFrame, cwu_df: pd.DataFrame, max_weight: float) -> pd.DataFrame:
        """Create cartesian product of CO and CWU sources with calculated weights."""
        if co_df.empty or cwu_df.empty:
            return pd.DataFrame(columns=[COLUMN_CO_SOURCE, COLUMN_CWU_SOURCE, COLUMN_PAIR_WEIGHT])

        # Create cartesian product
        co_df_repeated = co_df.loc[co_df.index.repeat(len(cwu_df))].reset_index(drop=True)
        cwu_df_repeated = pd.concat([cwu_df] * len(co_df), ignore_index=True)

        # Calculate pair weights
        pair_weights = co_df_repeated["weight"] * cwu_df_repeated["weight"] * max_weight

        result_df = pd.DataFrame(
            {
                COLUMN_CO_SOURCE: co_df_repeated["heat_source_classified"],
                COLUMN_CWU_SOURCE: cwu_df_repeated["heat_source_classified"],
                COLUMN_PAIR_WEIGHT: pair_weights,
            }
        )

        return result_df

    def _remove_trash_pairs(self, pairs_df: pd.DataFrame) -> pd.DataFrame:
        """Remove junk pairs using iterative pruning."""
        if len(pairs_df) <= 1:
            return pairs_df

        df = pairs_df.copy()

        # While min weight < threshold and more than 1 row
        while df[COLUMN_PAIR_WEIGHT].min() < self.trash_threshold and len(df) > 1:
            min_weight = df[COLUMN_PAIR_WEIGHT].min()
            min_rows = df[COLUMN_PAIR_WEIGHT] == min_weight

            if min_rows.sum() == 1:
                # Remove single min-weight row
                df = df[~min_rows].copy()
                # Redistribute its weight equally to remaining rows
                df[COLUMN_PAIR_WEIGHT] += min_weight / len(df)
            else:
                # Multiple rows with same min weight, remove one randomly
                # For deterministic behavior, remove the first one
                first_min_index = df[min_rows].index[0]
                df = df.drop(first_min_index).copy()
                # Redistribute its weight equally to remaining rows
                df[COLUMN_PAIR_WEIGHT] += min_weight / len(df)

        return df

    def _extract_building_metadata(self, group_df: pd.DataFrame) -> dict:
        """Extract building-level attributes from a building group.

        Building-level attributes are those that have consistent values across all
        rows for a given merged_id (e.g., spatial data, building classification).
        CEEB device-specific columns are excluded, but building-level columns are preserved.

        Args:
            group_df: DataFrame containing all rows for a single merged_id

        Returns:
            Dictionary of building-level column names and their values
        """
        # Get first row (all building-level attributes should be identical across rows)
        first_row = group_df.iloc[0]

        # Extract all columns except device-specific ones
        metadata = {}
        for col in group_df.columns:
            # Include columns that are either:
            # 1. Not in the device-specific exclusion list, OR
            # 2. Explicitly marked as building-level columns
            if col not in CEEB_DEVICE_SPECIFIC_COLUMNS or col in BUILDING_LEVEL_COLUMNS:
                metadata[col] = first_row[col]

        return metadata

    def _process_buildings(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process each building to create weighted heat source pairs."""
        results = []

        # Group by building
        grouped = df.groupby("merged_id")

        _logger.info(f"Processing {len(grouped)} buildings...")

        for _merged_id, group in grouped:
            # Extract all building-level metadata once per building
            building_metadata = self._extract_building_metadata(group)

            # Get building type for processing logic
            building_type = group["Rodzaj_budynku_A"].iloc[0]
            n_apartments = self._estimate_apartment_count(group)

            # Estimate max heat sources for this building
            max_heat_sources = self._estimate_max_heat_sources(group, n_apartments)

            # Calculate max_weight (from R logic)
            max_weight = self.max_weight

            # Select CO sources
            co_sources = self._select_weighted_sources(group, max_heat_sources, self.central_hierarchy, "C.O.")

            # Select CWU sources
            cwu_sources = self._select_weighted_sources(group, max_heat_sources, self.cwu_hierarchy, "C.W.U.")

            # Create pairs
            pairs = self._create_pairs_and_weights(co_sources, cwu_sources, max_weight)

            # Remove trash pairs
            if not pairs.empty:
                pairs = self._remove_trash_pairs(pairs)

                # Map to final canonical names
                # Convert to string first to avoid categorical fillna issues
                co_source_orig = pairs[COLUMN_CO_SOURCE].astype(str)
                cwu_source_orig = pairs[COLUMN_CWU_SOURCE].astype(str)

                pairs[COLUMN_CO_SOURCE] = co_source_orig.map(self.final_mapping).fillna(co_source_orig)
                pairs[COLUMN_CWU_SOURCE] = cwu_source_orig.map(self.final_mapping).fillna(cwu_source_orig)

                # Preserve original weight column from source selection before renaming pair_weight
                # The 'weight' column contains the source weight from co_sources
                # This is needed for downstream processing (e.g., creating_operat_losowania)
                if not co_sources.empty:
                    pairs["weight"] = (
                        co_sources["weight"]
                        .repeat(len(cwu_sources) if len(cwu_sources) > 0 else 1)
                        .reset_index(drop=True)
                    )
                pairs = pairs.rename(columns={COLUMN_PAIR_WEIGHT: "proportion"})

                # Add analysis-derived columns
                pairs["n_apartments"] = n_apartments
                pairs["max_heat_sources"] = max_heat_sources
                pairs["building_type"] = building_type

                # Add all building-level metadata from input
                # Skip merged_id as it's already in building_metadata
                for col, value in building_metadata.items():
                    if col not in pairs.columns:
                        pairs[col] = value

                results.append(pairs)

        if results:
            final_df = pd.concat(results, ignore_index=True)
            return final_df
        else:
            # Return empty DataFrame with core columns
            # Note: In actual use, this is unlikely to occur as buildings should have heat sources
            return pd.DataFrame(
                columns=[
                    "merged_id",
                    COLUMN_CO_SOURCE,
                    COLUMN_CWU_SOURCE,
                    "weight",
                    "proportion",
                    "n_apartments",
                    "max_heat_sources",
                    "building_type",
                ]
            )

    def _optimize_string_columns_to_categorical(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert low-cardinality string columns to categorical for memory optimization."""
        df = df.copy()
        # Convert heat source columns to categorical
        categorical_columns = [
            "heat_source_classified",
            "Źródło_ciepła",
            "Rodzaj_budynku_A",
        ]

        for col in categorical_columns:
            if col in df.columns:
                try:
                    df[col] = df[col].astype("category")
                except Exception:
                    # Best-effort conversion, ignore failures
                    pass

        return df
