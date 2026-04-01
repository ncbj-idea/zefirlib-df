import logging
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

from datafusion.configs.pvgis_config import PVGISConfig
from datafusion.database.models.address_point import AddressPoint
from datafusion.database.models.pvgis import PVGis

_logger = logging.getLogger(__name__)


class PVGISMerger:
    def __init__(
        self,
        config: PVGISConfig,
        engine: Engine,
    ) -> None:
        self.config = config
        self.engine = engine
        self.radius = config.radius
        self._table_names = [AddressPoint.__tablename__, PVGis.__tablename__]
        self.data: dict[str, pd.DataFrame] = {}

    def get_data(self) -> None:
        for table_name in self._table_names:
            _logger.info(f"Getting data for {table_name}")
            self.data[table_name] = self.get_data_data_for_coords(
                table_name, self.config.lon, self.config.lat, self.radius
            )

    def save_data(self, file_name: str = "pvgis_merge.xlsx") -> None:
        if self.config.output_path is not None:
            output_file = Path(self.config.output_path) / file_name
            output_file.parent.mkdir(parents=True, exist_ok=True)
            _logger.info(f"Saving data to {output_file}")
            with pd.ExcelWriter(output_file) as writer:
                for sheet, data in self.data.items():
                    data.to_excel(writer, sheet_name=sheet, index=False)
        else:
            raise ValueError("Output path not provided in config file for PVGISConfig")

    def get_data_data_for_coords(self, table_name: str, lon: float, lat: float, radius: float) -> pd.DataFrame:
        query_string = f"SELECT t1.* \
            FROM {table_name} AS t1 \
                WHERE \
                    ST_DWithin(\
                        geography(ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)), \
                        geography(ST_SetSRID(ST_MakePoint(t1.longitude, t1.latitude), 4326)), \
                        {radius} ) "
        df = pd.read_sql_query(query_string, self.engine)
        return df
