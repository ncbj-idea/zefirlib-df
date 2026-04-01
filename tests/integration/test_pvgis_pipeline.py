import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from datafusion.configs.config import Config
from datafusion.database.db_settings import DBSettings
from datafusion.pvgis.data_merger import PVGISMerger
from datafusion.readers.pvgis_reader import PVGISReader
from tests.conftest import get_test_engine


def test_pvgis_pipeline(
    mock_config: Config,
    mock_database_settings: DBSettings,
) -> None:
    if os.getenv("CI", False) == "true":
        pytest.skip("Skipping tests in CI environment")
        return
    test_engine = get_test_engine(mock_database_settings)
    pvgis_reader = PVGISReader(mock_config.pvgis, test_engine)
    pvgis_reader.run()

    with test_engine.connect() as conn:
        df = pd.read_sql_table(
            table_name="pvgis",
            con=conn,
        )
    for col in ["time", "P", "Gi", "T2m", "latitude", "longitude", "peakpower"]:
        assert col in df.columns


def test_pvgis_merger_pipeline(
    mock_config: Config,
    mock_database_settings: DBSettings,
) -> None:
    if os.getenv("CI", False) == "true":
        pytest.skip("Skipping tests in CI environment")
        return
    test_engine = get_test_engine(mock_database_settings)
    with tempfile.TemporaryDirectory() as tmp_dir:
        mock_config.pvgis.output_path = tmp_dir
        pvgis_reader = PVGISReader(mock_config.pvgis, test_engine)
        pvgis_reader.run()
        pvgis_merger = PVGISMerger(mock_config.pvgis, test_engine)
        pvgis_merger.get_data()
        pvgis_merger.save_data("test_merge.xlsx")

        excel_path = Path(tmp_dir) / "test_merge.xlsx"
        excel_data = pd.read_excel(excel_path, sheet_name=None)

        for name, df in excel_data.items():
            assert name in ["address_point", "pvgis"]
            assert isinstance(df, pd.DataFrame)
