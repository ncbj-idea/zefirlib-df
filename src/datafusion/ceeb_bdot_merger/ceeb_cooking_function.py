from __future__ import annotations

import logging
from collections.abc import Iterable

import pandas as pd

from datafusion.configs.merge_config import BdotParams, CeebParams

_logger = logging.getLogger(__name__)

# Constants
DEFAULT_BOOL_VALUE = "Tak"
DEFAULT_DEVICE_COUNT = 1
FILL_VALUE = 0


def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names by replacing spaces with underscores.

    Args:
        df: DataFrame to standardize

    Returns:
        DataFrame with standardized column names
    """
    df = df.copy()
    df.columns = [str(col).replace(" ", "_") for col in df.columns]
    return df


def _ensure_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Ensure that specified columns exist in the dataframe, adding them as NA if missing.

    Args:
        df: The dataframe to check
        columns: Column names that should exist

    Returns:
        DataFrame with all specified columns present
    """
    df = df.copy()
    missing_cols = [c for c in columns if c not in df.columns]
    if missing_cols:
        df[missing_cols] = pd.NA
    return df


class CeebCleaner:
    """CEEB cleaning function.

    Makes some basic cleaning in CEEB data by renaming address columns and filtering
    out rows with missing data in specified columns.

    New names for address should come from building data.
    """

    def __init__(
        self,
        original_address_number_column: str,
        original_street_column: str,
        standardized_address_number_column: str,
        standardized_street_column: str,
        na_filter_columns: Iterable[str],
        log_file: bool = False,
    ):
        """Initialize the CEEB cleaner.

        Args:
            original_address_number_column: Column name that points to the number in address
            original_street_column: Column name that points to the street name
            standardized_address_number_column: New name for the number in address
            standardized_street_column: New name for street name
            na_filter_columns: Names of the columns where missing data filter should be applied
            log_file: Whether to print more information in logs
        """
        self.original_address_number_column = original_address_number_column
        self.original_street_column = original_street_column
        self.standardized_address_number_column = standardized_address_number_column
        self.standardized_street_column = standardized_street_column
        self.na_filter_columns = list(na_filter_columns)
        self.log_file = log_file

    def clean(self, data: pd.DataFrame) -> pd.DataFrame:
        """Clean CEEB data by renaming columns and filtering missing data.

        Args:
            data: DataFrame, klasy or urzadzenia (CEEB reports)

        Returns:
            Cleaned DataFrame with renamed columns and filtered missing data
        """
        df = standardize_column_names(data)
        df.rename(
            columns={
                self.original_address_number_column: self.standardized_address_number_column,
                self.original_street_column: self.standardized_street_column,
            },
            inplace=True,
            errors="ignore",
        )
        initial_rows = len(df)
        if self.na_filter_columns:
            df.dropna(subset=self.na_filter_columns, inplace=True)
        if self.log_file:
            final_rows = len(df)
            _logger.info(f"Number of deleted rows due to missing data is: {initial_rows - final_rows}")
        return df


class KlasyCreator:
    """Change klasy data frame from long to wide format.

    In terms of devices, urzadzenia table has wide data format. This class transforms
    the long format klasy data to wide format for merging with device data.

    Missing values, which appear after data transformation, are replaced by zero.
    """

    def __init__(self, grouping_columns: list[str], device_class_column: str):
        """Initialize the klasy creator.

        Args:
            grouping_columns: Names of columns which identify building, type of declaration and class of device
            device_class_column: Column name that points to device class
        """
        self.grouping_columns = grouping_columns
        self.device_class_column = device_class_column

    def create(self, data: pd.DataFrame) -> pd.DataFrame:
        """Create wide format DataFrame from long format klasy data.

        Args:
            data: DataFrame, klasy - CEEB report

        Returns:
            DataFrame in wide format with device classes as columns
        """
        res_df = data[self.grouping_columns].copy().dropna()
        res_df = res_df.groupby(self.grouping_columns).size().reset_index(name="n")
        id_vars = [v for v in self.grouping_columns if v != self.device_class_column]
        if not id_vars:
            return res_df.pivot_table(columns=self.device_class_column, values="n", fill_value=0).reset_index()
        pivoted = res_df.pivot_table(
            index=id_vars, columns=self.device_class_column, values="n", fill_value=0
        ).reset_index()
        pivoted.columns.name = None
        return pivoted


class CeebMerger:
    """CEEB merging data condition on value.

    Allows merging CEEB tables, depending on value in a given column. Merging tables
    can occur only when in urzadzenia table in target column is given value.
    This is because the classes are applied only to specific devices.

    After merging data, missing values in columns which refer to devices class are replaced by zero.
    """

    def __init__(
        self,
        merge_columns: list[str],
        boiler_filter_values: Iterable[str],
        boiler_type_column: str,
    ):
        """Initialize the CEEB merger.

        Args:
            merge_columns: Names of columns that should be used in merging tables
            boiler_filter_values: Values that will be checked in boiler_type_column
            boiler_type_column: Name of the column in which the condition will be checked
        """
        self.merge_columns = merge_columns
        self.boiler_filter_values = set(boiler_filter_values)  # Use set for O(1) lookup
        self.boiler_type_column = boiler_type_column

    def merge(self, urzadzenia: pd.DataFrame, klasy: pd.DataFrame) -> pd.DataFrame:
        """Merge urzadzenia and klasy DataFrames based on device type conditions.

        Args:
            urzadzenia: DataFrame, urzadzenia - CEEB report
            klasy: DataFrame, klasy - CEEB report

        Returns:
            Merged DataFrame with device classes applied only to specific devices
        """
        devices_df = _ensure_columns(urzadzenia, self.merge_columns)
        kl = _ensure_columns(klasy, self.merge_columns)
        zero_cols = [c for c in kl.columns if c not in self.merge_columns]

        # Create mask once for better performance
        boiler_mask = devices_df[self.boiler_type_column].isin(self.boiler_filter_values)
        with_boiler = devices_df[boiler_mask]
        without_boiler = devices_df[~boiler_mask]

        merged = with_boiler.merge(kl, on=self.merge_columns, how="left")
        res = pd.concat([merged, without_boiler], ignore_index=True)
        res[zero_cols] = res[zero_cols].fillna(FILL_VALUE)
        return standardize_column_names(res)


class DeviceImputer:
    """Making imputation and correction in number of devices.

    CEEB report has two columns related to number of devices. They need some
    cleaning due to missing values or illogical values.

    CEEB report has two columns related to number of devices - installed and in use.
    It is possible that in one column will be missing value or in use has higher value than installed.
    If missing, then value from other variable is imputed. If in use has higher value than
    based on preferred_count_source argument, installed are increased to in use or in use is decreased to
    installed number of devices.
    """

    def __init__(
        self,
        installed_devices_count_column: str,
        devices_in_use_count_column: str,
        hot_water_status_column: str,
        central_heating_status_column: str,
        preferred_count_source: str,
    ):
        """Initialize the device imputer.

        Args:
            installed_devices_count_column: Column name that points to number of installed devices
            devices_in_use_count_column: Column name that points to devices in use
            hot_water_status_column: Column name that points to hot water (CWU) status
            central_heating_status_column: Column name that points to central heating (CO) status
            preferred_count_source: installed_devices_count_column or devices_in_use_count_column, which value
                should be taken when devices_in_use_count_column is greater than installed_devices_count_column
                (increase installed or decrease in use)
        """
        self.installed_devices_count_column = installed_devices_count_column
        self.devices_in_use_count_column = devices_in_use_count_column
        self.hot_water_status_column = hot_water_status_column
        self.central_heating_status_column = central_heating_status_column
        self.preferred_count_source = preferred_count_source

    def impute(self, data: pd.DataFrame) -> pd.DataFrame:
        """Impute and correct number of devices in the merged CEEB reports.

        Args:
            data: DataFrame, merged ceeb's reports

        Returns:
            DataFrame with imputed and corrected device numbers
        """
        df = _ensure_columns(
            data,
            [
                self.installed_devices_count_column,
                self.devices_in_use_count_column,
                self.hot_water_status_column,
                self.central_heating_status_column,
            ],
        )

        # Convert to numeric once
        df[self.installed_devices_count_column] = pd.to_numeric(
            df[self.installed_devices_count_column], errors="coerce"
        )
        df[self.devices_in_use_count_column] = pd.to_numeric(df[self.devices_in_use_count_column], errors="coerce")

        # Handle different types of missing values
        self._handle_missing_device_counts(df)
        self._handle_missing_boolean_values(df)
        self._handle_inconsistent_counts(df)

        return df

    def _handle_missing_device_counts(self, df: pd.DataFrame) -> None:
        """Handle missing values in device count columns."""
        # Both missing - set to default
        mask_both_na = df[self.installed_devices_count_column].isna() & df[self.devices_in_use_count_column].isna()
        df.loc[mask_both_na, self.installed_devices_count_column] = DEFAULT_DEVICE_COUNT

        # Cross-fill missing values
        df[self.devices_in_use_count_column] = df[self.devices_in_use_count_column].fillna(
            df[self.installed_devices_count_column]
        )
        df[self.installed_devices_count_column] = df[self.installed_devices_count_column].fillna(
            df[self.devices_in_use_count_column]
        )

        # Both zero - set to default
        mask_both_zero = (df[self.installed_devices_count_column] == 0) & (df[self.devices_in_use_count_column] == 0)
        df.loc[mask_both_zero, self.installed_devices_count_column] = DEFAULT_DEVICE_COUNT

    def _handle_missing_boolean_values(self, df: pd.DataFrame) -> None:
        """Handle missing values in boolean columns."""
        mask_both_na = df[self.central_heating_status_column].isna() & df[self.hot_water_status_column].isna()
        df.loc[mask_both_na, self.central_heating_status_column] = DEFAULT_BOOL_VALUE

        # Cross-fill boolean columns
        df[self.hot_water_status_column] = df[self.hot_water_status_column].fillna(
            df[self.central_heating_status_column]
        )
        df[self.central_heating_status_column] = df[self.central_heating_status_column].fillna(
            df[self.hot_water_status_column]
        )

    def _handle_inconsistent_counts(self, df: pd.DataFrame) -> None:
        """Handle cases where devices_in_use_count_column > installed_devices_count_column."""
        mask_in_use_gt_installed = df[self.devices_in_use_count_column] > df[self.installed_devices_count_column]

        if self.preferred_count_source == self.installed_devices_count_column:
            # Decrease devices_in_use_count_column to match installed_devices_count_column
            df.loc[mask_in_use_gt_installed, self.devices_in_use_count_column] = df.loc[
                mask_in_use_gt_installed, self.installed_devices_count_column
            ]
        else:
            # Increase installed_devices_count_column to match devices_in_use_count_column
            df.loc[mask_in_use_gt_installed, self.installed_devices_count_column] = df.loc[
                mask_in_use_gt_installed, self.devices_in_use_count_column
            ]


class CeebPipeline:
    """Complete pipeline for processing CEEB reports.

    Orchestrates the entire process of cleaning, transforming, merging, and imputing
    CEEB device and class data according to configuration parameters.
    """

    def __init__(self, ceeb_params: CeebParams, bdot_params: BdotParams, expanded_logs: bool):
        """Initialize the CEEB pipeline with configuration parameters.

        Args:
            ceeb_params: Configuration parameters for CEEB data processing
            bdot_params: Configuration parameters for BDOT data (address column names)
            expanded_logs: Whether to enable expanded logging
        """
        # build device and class cleaners from config
        new_num = bdot_params.bdot_number_col
        new_str = bdot_params.bdot_street_col
        self.device_cleaner = CeebCleaner(
            original_address_number_column=ceeb_params.ceeb_number_param,
            original_street_column=ceeb_params.ceeb_street_param,
            standardized_address_number_column=new_num,
            standardized_street_column=new_str,
            na_filter_columns=ceeb_params.ceeb_important_col,
            log_file=expanded_logs,
        )
        self.class_cleaner = CeebCleaner(
            original_address_number_column=ceeb_params.ceeb_diverge,
            original_street_column=ceeb_params.ceeb_street_param,
            standardized_address_number_column=new_num,
            standardized_street_column=new_str,
            na_filter_columns=ceeb_params.ceeb_summary,
            log_file=expanded_logs,
        )
        self.creator = KlasyCreator(
            grouping_columns=ceeb_params.ceeb_summary,
            device_class_column=ceeb_params.ceeb_class_col,
        )
        self.merger = CeebMerger(
            merge_columns=ceeb_params.ceeb_merger,
            boiler_filter_values=ceeb_params.ceeb_boiler,
            boiler_type_column=ceeb_params.ceeb_device_col,
        )
        self.imputer = DeviceImputer(
            installed_devices_count_column=ceeb_params.ceeb_nmb_col,
            devices_in_use_count_column=ceeb_params.ceeb_eksp_col,
            hot_water_status_column=ceeb_params.ceeb_cwu,
            central_heating_status_column=ceeb_params.ceeb_co,
            preferred_count_source=ceeb_params.ceeb_eksp_col,
        )

    def run(self, devices: pd.DataFrame, classes: pd.DataFrame) -> pd.DataFrame:
        """Run the complete CEEB processing pipeline.

        Args:
            devices: DataFrame containing device data (urzadzenia)
            classes: DataFrame containing class data (klasy)

        Returns:
            Processed and merged DataFrame with imputed device numbers
        """
        cleaned_devices = self.device_cleaner.clean(devices)
        cleaned_classes = self.class_cleaner.clean(classes)
        cleaned_classes = self.creator.create(cleaned_classes)
        merged = self.merger.merge(cleaned_devices, cleaned_classes)
        return self.imputer.impute(merged)
