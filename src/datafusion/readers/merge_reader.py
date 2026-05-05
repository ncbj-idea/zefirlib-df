import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from datafusion.ceeb_bdot_merger.address_flag_list import address_flag_list
from datafusion.ceeb_bdot_merger.bdot_modification_functions import (
    BdotModificationPipeline,
)

# Helper modules used to reproduce r_to_py/main.py logic
from datafusion.ceeb_bdot_merger.ceeb_cooking_function import CeebPipeline
from datafusion.ceeb_bdot_merger.clean_address_functions import (
    AddressCleaner,
    clean_street_name,
)
from datafusion.ceeb_bdot_merger.heat_source_analyzer import HeatSourceAnalyzer
from datafusion.ceeb_bdot_merger.joining_functions import magic_join
from datafusion.configs.global_config import GlobalConfig
from datafusion.configs.merge_config import MergeConfig
from datafusion.constants import (
    TABLE_CEEB_CLASSES,
    TABLE_CEEB_DEVICES,
    TABLE_HEAT_SOURCE_RESULT,
    TABLE_NON_MERGED_BDOT,
    TABLE_PROCESSED_BDOT,
)
from datafusion.database.db_settings import DBSettings
from datafusion.reporting.reporting import Reporting
from datafusion.utils.crud import save_dataframe_to_db

_logger = logging.getLogger(__name__)


EXCEL_MAX_ROWS = 1_048_576


class MergeReader:
    def __init__(
        self,
        config: MergeConfig,
        engine: Engine,
        db_settings: DBSettings,
    ) -> None:
        self.config = config
        self.engine = engine
        self.db_settings = db_settings

    def _safe_write_table(self, df: pd.DataFrame, xlsx_path: Path) -> Path:
        xlsx_path.parent.mkdir(parents=True, exist_ok=True)
        if len(df) <= EXCEL_MAX_ROWS:
            df.to_excel(xlsx_path, index=False)
            return xlsx_path
        csv_path = xlsx_path.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        return csv_path

    def _load_ceeb_dataframe(self, table_name: str) -> pd.DataFrame:
        inspector = inspect(self.engine)
        if table_name not in inspector.get_table_names():
            raise RuntimeError(f"Table '{table_name}' does not exist in the database.")
        query = f"SELECT * FROM {table_name} WHERE terc = '{self.config.terc}'"
        df = pd.read_sql(query, self.engine)
        if df.empty:
            raise RuntimeError(f"Table '{table_name}' is empty or no rows for terc='{self.config.terc}'.")
        return df

    def _load_buildings_report(self) -> pd.DataFrame:
        report_handler = Reporting(
            config=GlobalConfig(terc=self.config.terc),
            db_engine=self.engine,
        )  # lightweight config
        return report_handler.run()

    def _save_result_to_database(self, df: pd.DataFrame, table_name: str) -> None:
        _logger.info("Saving '%s' to database", table_name)
        df = df.copy()
        df["terc"] = self.config.terc
        save_dataframe_to_db(self.engine, df, table_name)

    def _save_result_to_excel(self, df: pd.DataFrame, filename: str) -> None:
        if self.config.output_path is None:
            return
        out_path = self.config.output_path / filename
        saved = self._safe_write_table(df, out_path)
        _logger.info("Result saved to %s", saved)

    def run(self) -> None:
        _logger.info("Running MergeReader...")

        # Load inputs from DB
        ceeb_devices = self._load_ceeb_dataframe(TABLE_CEEB_DEVICES)
        ceeb_classes = self._load_ceeb_dataframe(TABLE_CEEB_CLASSES)
        buildings_report = self._load_buildings_report()

        # Pull config shortcuts
        ceeb_params = self.config.ceeb_params
        bdot_params = self.config.bdot_params

        expanded_logs = self.config.expanded_logs
        bdot_street_col = bdot_params.bdot_street_col
        bdot_number_col = bdot_params.bdot_number_col

        # CEEB pipeline (devices + classes merge and imputation)
        ceeb_pipeline = CeebPipeline(ceeb_params, bdot_params, expanded_logs)
        ceeb_all = ceeb_pipeline.run(ceeb_devices, ceeb_classes)

        # Address cleaning
        clean_buildings_report = clean_street_name(data=buildings_report, street_column=bdot_street_col)
        if "duplication_id" not in ceeb_all.columns:
            ceeb_all["duplication_id"] = pd.NA
            ceeb_all["duplication_id"] = ceeb_all["duplication_id"].astype("Int64")

        flags_list = address_flag_list(
            data=clean_buildings_report,
            street_name=bdot_street_col,
            house_number_column=bdot_number_col,
        )

        address_cleaner = AddressCleaner(
            data=ceeb_all,
            bdot_params=bdot_params,
            ceeb_params=ceeb_params,
            flags_list=flags_list,
            duplication_id="duplication_id",
            log_file=expanded_logs,
        )
        clean_ceeb = address_cleaner.clean()

        # BDOT modification
        bdot_pipeline = BdotModificationPipeline(
            config=self.config,
        )
        pyszny_bdot = bdot_pipeline.run(clean_buildings_report)
        self._save_result_to_database(pyszny_bdot, TABLE_PROCESSED_BDOT)

        """ Join CEEB data with BDOT """
        merged_ceeb_bdot = magic_join(
            building_data=pyszny_bdot,
            ceeb_data=clean_ceeb,
            address_key="bdot_key",
            street_mod_var="ulica_mod",
            number_var=bdot_number_col,
            street_var=bdot_street_col,
            similarity_method=self.config.string_method,
            max_similarity_distance=self.config.string_max_distance,
            similarity_threshold=self.config.string_param,
        )

        # Heat source analysis
        heat_analyzer = HeatSourceAnalyzer(self.config.heat_source_analysis_params)
        heat_source_result = heat_analyzer.run(merged_ceeb_bdot["merged_data"])

        # Persist results
        self._save_result_to_database(heat_source_result, TABLE_HEAT_SOURCE_RESULT)
        self._save_result_to_database(merged_ceeb_bdot["unmerged_building_data"], TABLE_NON_MERGED_BDOT)
        # self._save_result_to_excel(pyszny_bdot, f"pyszny_bdot_{self.config.terc}.xlsx")

        _logger.info("MergeReader done.")
