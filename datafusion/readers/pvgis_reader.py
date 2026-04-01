import json
import logging
from collections import defaultdict

import pandas as pd
import requests
from sqlalchemy.engine import Engine

from datafusion.configs.pvgis_config import PVGISConfig
from datafusion.database.models.pvgis import PVGis
from datafusion.readers.base_reader import Reader

_logger = logging.getLogger(__name__)

COLUMN_MAPPING = {"G(i)": "Gi"}


class PVGISReader(Reader):
    """
    A class used to read data from PVGIS database.

    This class handles importing PVGIS data to database, which includes
    importing information from online database.
    The results are saved to output database.
    """

    def __init__(
        self,
        config: PVGISConfig,
        engine: Engine,
    ) -> None:
        """
        Constructor for KIUTReader class.

        Args:
            config: KIUTConfig instance
            engine: SQLAlchemy engine instance
            data: Data downloaded from online database
        """

        self.config = config
        self.engine = engine

    def run(self) -> None:
        """
        Executes PVGIS reading process
        """
        _logger.info("Getting meta data")
        self.get_meta_obj(
            table_name=PVGis.__tablename__,
            config=self.config,
            engine=self.engine,
        )
        _logger.info("Reading data from online database")
        data = self._read_data()
        data = self._transform_data(data)
        data = self._add_aditional_columns(data)
        prepared_data = self._set_mapping(data)
        _logger.info("Saving data to database")
        prepared_data.to_sql(
            name="pvgis",
            con=self.engine,
            if_exists="replace",
            index=True,
            index_label="id",
        )
        _logger.info("Commiting changes to database")

    def _set_mapping(self, data: pd.DataFrame) -> pd.DataFrame:
        data = data.rename(columns=COLUMN_MAPPING)
        return data

    def _add_aditional_columns(self, data: pd.DataFrame) -> pd.DataFrame:
        data["latitude"] = self.config.lat
        data["longitude"] = self.config.lon
        data["peakpower"] = self.config.peakpower
        data["loss"] = self.config.loss
        return data

    def _transform_data(self, data: list) -> pd.DataFrame:
        tmp_data = defaultdict(list)
        for dict_ in data:
            for item, value in dict_.items():
                tmp_data[item].append(value)
        df = pd.DataFrame(tmp_data)
        _logger.info(df["time"])
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], format="%Y%m%d:%H%M", errors="coerce")
        return df

    def _read_data(self) -> list:
        response = requests.get(self.config.base_url, params=self.config.url_params)
        return json.loads(response.text)["outputs"]["hourly"]
