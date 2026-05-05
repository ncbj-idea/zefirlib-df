import logging

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from datafusion.configs.global_config import GlobalConfig
from datafusion.reporting.constants import (
    BUD_UWZGLEDNIANY_POWYZEJ,
    CZY_OGRZEWANY,
    FUNKCJA_OGOLNA,
    FUNKCJA_SZCZEGOLOWA,
    FUNKCJA_SZCZEGOLOWA_1,
    FUNKCJA_SZCZEGOLOWA_2,
    FUNKCJA_SZCZEGOLOWA_3,
    M2_MIN_DO_SIECI,
    MIN_POW_ZABUD,
    NAZWA_PARAMETRU,
    ODLEGLOSC_OD_SIECI,
    PARAMETRY,
    PODL_DO_GAZ_I_SYSTEM_GS,
    POW_POWYZEJ,
    POW_UZYT_OGRZ_PARTERU_Z_WYLACZENIEM,
    POW_UZYTKOWA_OGRZEWANA,
    POZA_PODL_DO_SIECI_GAZ_I_CIEP_N,
    PROCENT_POWIERZCHNI_OGRZEWANYCH_BUDYNKOW,
    QUERY_GAS_DISTANCE,
    QUERY_HEAT_DISTANCE,
    QUERY_LICZBA_KONDYGNACJI,
    QUERY_POW_OBRYSU_M2,
    TYLKO_PODL_DO_GAZU_G,
    TYLKO_PODL_DO_SYSTEM_S,
    WSPOLCZYNNIK_POWIERZCHNI_UZYTKOWEJ_DO_POWIERZCHNI_ZABUDOWY,
    ZALEZNE_OD_FUNKCJI_OGOLNEJ,
    ZALEZNE_OD_FUNKCJI_SZCZEGOLOWEJ,
)
from datafusion.reporting.utils import get_building_parameters_path

_logger = logging.getLogger(__name__)


class ReportError(Exception):
    pass


class Reporting:
    def __init__(self, config: GlobalConfig, db_engine: Engine) -> None:
        self.config = config
        self.db_engine = db_engine

    def run(self) -> pd.DataFrame:
        """
        Create dataframe with building data and optionally save it to xlsx file.
        """

        extended_data = self._create_buildings_report()
        output_path = self.config.output_folder
        if extended_data.empty:
            _logger.info(f"No data for given terc: '{self.config.terc}' in the database!")
            return pd.DataFrame()

        if output_path:
            output_file_path = output_path / self.config.terc / f"buildings_report_{self.config.terc}.xlsx"
            output_file_path.parent.mkdir(parents=True, exist_ok=True)
            extended_data.to_excel(output_file_path, merge_cells=False, index=False)
            _logger.info(f"SAVED TO: {output_file_path}")

        return extended_data

    def _create_buildings_report(self) -> pd.DataFrame:
        """
        Calculation and processing buildings' dataframe.

        Returns:
            - DataFrame: extended building data.
        """
        city_data = self._get_data_from_db()

        with pd.ExcelFile(get_building_parameters_path()) as reader:
            params = self.get_parameters_from_template(reader)
            df_funkcja_szczegolowa = pd.read_excel(
                reader,
                sheet_name=ZALEZNE_OD_FUNKCJI_SZCZEGOLOWEJ,
            )
            df_funkcja_ogolna = pd.read_excel(
                reader,
                sheet_name=ZALEZNE_OD_FUNKCJI_OGOLNEJ,
            )

        df = self.get_extended_buildings_data(city_data, df_funkcja_szczegolowa, df_funkcja_ogolna, params)
        return df

    @staticmethod
    def _get_split_dict(dct: dict[str, list[int | float]]) -> dict[str, int | float]:
        return {k: v[0] for k, v in dct.items()}

    def get_parameters_from_template(self, reader: pd.ExcelFile | None = None) -> dict[str, int | float]:
        """
        Read parameters from mock xlsx file

        Args:
            reader: Optional ExcelFile object to read from.

        Returns:
            - Parameters dictionary.
        """
        if reader is not None:
            df_params = pd.read_excel(reader, sheet_name=PARAMETRY)
        else:
            df_params = pd.read_excel(get_building_parameters_path(), sheet_name=PARAMETRY)

        dict_temp = df_params.set_index(NAZWA_PARAMETRU).T.to_dict(orient="list")
        result = self._get_split_dict(dict_temp)
        return result

    def _get_data_from_db(self) -> pd.DataFrame:
        """
        Fetch data from database using postgres procedure with fallback mechanism.

        Uses fast KNN-based ordering by default, but falls back to ST_Distance-based
        ordering if validation fails or if safe mode is enabled.

        Returns:
            - Dataframe with raw data from db.
        """
        # Try fast path first
        try:
            data = self._fetch_from_db("get_gis_data_for_given_terc")
        except (SQLAlchemyError, ReportError) as e:
            _logger.warning(f"Optimized function failed, trying fallback: {str(e)[:100]}")
            data = self._fetch_from_db("get_gis_data_for_given_terc_safe")
            _logger.info(f"Fallback query completed for TERC {self.config.terc} ")

        # Process the data
        data[FUNKCJA_SZCZEGOLOWA_1] = data[FUNKCJA_SZCZEGOLOWA].str[0]
        data[FUNKCJA_SZCZEGOLOWA_2] = data[FUNKCJA_SZCZEGOLOWA].str[1]
        data[FUNKCJA_SZCZEGOLOWA_3] = data[FUNKCJA_SZCZEGOLOWA].str[2]
        data["other"] = data["other"].astype(str).str[1:-1]
        return data

    def _fetch_from_db(self, func_name: str) -> pd.DataFrame:
        """
        Execute SQL query to fetch data from database.

        Args:
            func_name: Name of the SQL function to call

        Returns:
            - Dataframe with raw data from db.
        """
        stm = text(f"SELECT *, st_astext(geom) geom_wkt FROM {func_name}(:terc)")
        return pd.read_sql(stm, self.db_engine, params={"terc": self.config.terc})

    def get_extended_buildings_data(
        self,
        city_data: pd.DataFrame,
        df_funkcja_szczegolowa: pd.DataFrame,
        df_funkcja_ogolna: pd.DataFrame,
        params: dict[str, int | float],
    ) -> pd.DataFrame:
        """
        Fill dataframe with customized data

        Args:
            - city_data: DataFrame with buildings
            - df_funkcja_szczegolowa: funkcja szczegółowa mapper
            - df_funkcja_ogolna: funkcja ogólna mapper
            - params: input parameters
        Return:
            - DataFrame: updated building data
        """
        df = pd.merge(
            city_data.astype({FUNKCJA_OGOLNA: str}),
            df_funkcja_ogolna.astype({FUNKCJA_OGOLNA: str}),
            how="left",
            on=FUNKCJA_OGOLNA,
        )
        dfn = df.drop(columns=[FUNKCJA_SZCZEGOLOWA, CZY_OGRZEWANY])
        dfn = pd.merge(
            dfn.astype({FUNKCJA_SZCZEGOLOWA_1: str}),
            df_funkcja_szczegolowa.astype({FUNKCJA_SZCZEGOLOWA: str}),
            how="left",
            left_on=FUNKCJA_SZCZEGOLOWA_1,
            right_on=FUNKCJA_SZCZEGOLOWA,
        )
        if dfn.duplicated("id").any():
            duplicated_id = set(dfn[dfn.duplicated("id", keep=False)]["id"])
            _logger.error(f"Rows with ID:{duplicated_id} are duplicated.")
            raise ReportError(f"Rows with ID:{duplicated_id} are duplicated.")

        dfn[POW_UZYTKOWA_OGRZEWANA] = (
            dfn[QUERY_POW_OBRYSU_M2]
            * dfn[QUERY_LICZBA_KONDYGNACJI]
            * dfn[WSPOLCZYNNIK_POWIERZCHNI_UZYTKOWEJ_DO_POWIERZCHNI_ZABUDOWY]
            * dfn[PROCENT_POWIERZCHNI_OGRZEWANYCH_BUDYNKOW]
        )
        dfn[BUD_UWZGLEDNIANY_POWYZEJ] = (
            (dfn[POW_UZYTKOWA_OGRZEWANA] > params[MIN_POW_ZABUD])
            | (dfn[PROCENT_POWIERZCHNI_OGRZEWANYCH_BUDYNKOW] == 0.4)
        ).astype(int)

        dfn[POW_POWYZEJ] = np.where(dfn[BUD_UWZGLEDNIANY_POWYZEJ] == 1, dfn[POW_UZYTKOWA_OGRZEWANA], 0)
        dfn[POW_UZYT_OGRZ_PARTERU_Z_WYLACZENIEM] = dfn[POW_POWYZEJ] / dfn[QUERY_LICZBA_KONDYGNACJI]
        dfn[PODL_DO_GAZ_I_SYSTEM_GS] = (
            (dfn[QUERY_GAS_DISTANCE] < params[ODLEGLOSC_OD_SIECI])
            & (dfn[QUERY_HEAT_DISTANCE] < params[ODLEGLOSC_OD_SIECI])
            & (dfn[POW_UZYTKOWA_OGRZEWANA] > params[M2_MIN_DO_SIECI])
        )
        dfn[TYLKO_PODL_DO_GAZU_G] = (dfn[QUERY_GAS_DISTANCE] < params[ODLEGLOSC_OD_SIECI]) & ~dfn[
            PODL_DO_GAZ_I_SYSTEM_GS
        ]
        dfn[TYLKO_PODL_DO_SYSTEM_S] = (
            (dfn[QUERY_HEAT_DISTANCE] < params[ODLEGLOSC_OD_SIECI])
            & ~dfn[PODL_DO_GAZ_I_SYSTEM_GS]
            & (dfn[POW_UZYTKOWA_OGRZEWANA] > params[M2_MIN_DO_SIECI])
        )
        dfn[POZA_PODL_DO_SIECI_GAZ_I_CIEP_N] = (
            ~dfn[PODL_DO_GAZ_I_SYSTEM_GS] & ~dfn[TYLKO_PODL_DO_GAZU_G] & ~dfn[TYLKO_PODL_DO_SYSTEM_S]
        )
        return dfn
