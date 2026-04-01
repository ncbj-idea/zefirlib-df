from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from datafusion.database.db_settings import DBSettings
from datafusion.readers.ceeb_reader import CEEBReader  # Adjust the import as needed
from datafusion.utils.utils import FALSE_VALUES, TRUE_VALUES
from tests.mock_configs import CEEB_CONFIG


@pytest.fixture
def ceeb_reader() -> CEEBReader:
    config = MagicMock()
    config.__dict__ = CEEB_CONFIG

    engine = MagicMock()
    db_settings = MagicMock(spec=DBSettings)

    reader = CEEBReader(config=config, engine=engine, db_settings=db_settings)
    return reader


def test_run_single_data_success(ceeb_reader: CEEBReader) -> None:
    mock_df = pd.DataFrame({"col1": [1], "col2": [2]})

    with (
        patch.object(ceeb_reader, "read_from_file", return_value=mock_df),
        patch("datafusion.readers.ceeb_reader.validate_dataframe_by_schema"),
        patch.object(ceeb_reader, "_save_dataframe_to_db") as mock_save_method,
    ):
        ceeb_reader._import_id = 123

        ceeb_reader._run_single_data(ceeb_reader.config.ceeb_class_file_path, "ceeb_classes")

        mock_save_method.assert_called_once()
        assert "import_id" in mock_df.columns
        assert mock_df["import_id"].iloc[0] == ceeb_reader._import_id
        assert "terc" in mock_df.columns
        assert mock_df["terc"].iloc[0] == ceeb_reader.config.terc


def test_run_method(ceeb_reader: CEEBReader) -> None:
    with (
        patch.object(ceeb_reader, "_get_import_id", return_value=123) as mock_get_import_id,
        patch.object(ceeb_reader, "_run_single_data") as mock_run_single_data,
    ):
        ceeb_reader.run()

        mock_get_import_id.assert_called_once()
        mock_run_single_data.assert_any_call(ceeb_reader.config.ceeb_class_file_path, "ceeb_classes")
        mock_run_single_data.assert_any_call(ceeb_reader.config.ceeb_devices_file_path, "ceeb_devices")


def test_save_dataframe_to_db(ceeb_reader: CEEBReader) -> None:
    df = pd.DataFrame()
    with patch.object(pd.DataFrame, "to_sql") as mock_to_sql:
        ceeb_reader._save_dataframe_to_db(df, "ceeb_classes")
        mock_to_sql.assert_called_once()


def test_read_from_file(ceeb_reader: CEEBReader) -> None:
    with (
        patch("pandas.read_csv", return_value=pd.DataFrame({"col1": [1], "col2": [2]})) as mock_read_csv,
        patch("datafusion.readers.ceeb_reader.find_delimiter", return_value=",") as mock_find_delimiter,
    ):
        df = ceeb_reader.read_from_file(Path("mock/path/to/file.csv"))

        assert df.shape == (1, 2)
        assert "col1" in df.columns
        assert "col2" in df.columns
        mock_read_csv.assert_called_once_with(
            Path("mock/path/to/file.csv"),
            delimiter=",",
            true_values=TRUE_VALUES,
            false_values=FALSE_VALUES,
        )
        mock_find_delimiter.assert_called_once_with(Path("mock/path/to/file.csv"))
