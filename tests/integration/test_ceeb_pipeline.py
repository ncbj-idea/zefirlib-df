import pandas as pd

from datafusion.configs.config import Config
from datafusion.database.db_settings import DBSettings
from datafusion.readers.ceeb_reader import CEEBReader
from datafusion.utils.utils import FALSE_VALUES, TRUE_VALUES
from tests.conftest import get_test_engine
from tests.mock_configs import (
    CEEB_CLASSES_MOCK_FILE,
    CEEB_DEVICES_MOCK_FILE,
    ResourcesSubDirectory,
)
from tests.utils import get_resources


def test_ceeb_run(
    mock_config: Config,
    mock_database_settings: DBSettings,
) -> None:
    test_engine = get_test_engine(mock_database_settings)
    ceeb_reader = CEEBReader(
        config=mock_config.ceeb,
        engine=test_engine,
        db_settings=mock_database_settings,
    )
    ceeb_reader.run()

    with test_engine.connect() as conn:
        tested_df_device = pd.read_sql_table(
            table_name="ceeb_devices",
            con=conn,
        )
        tested_df_classes = pd.read_sql_table(
            table_name="ceeb_classes",
            con=conn,
        )
    mock_file_devices = get_resources(f"{ResourcesSubDirectory.CEEB}/{CEEB_DEVICES_MOCK_FILE}")
    mock_file_classes = get_resources(f"{ResourcesSubDirectory.CEEB}/{CEEB_CLASSES_MOCK_FILE}")
    expected_df_devices = pd.read_csv(
        mock_file_devices,
        true_values=TRUE_VALUES,
        false_values=FALSE_VALUES,
    )
    expected_df_classes = pd.read_csv(
        mock_file_classes,
        true_values=TRUE_VALUES,
        false_values=FALSE_VALUES,
    )

    assert tested_df_device["import_id"].iloc[0] == tested_df_classes["import_id"].iloc[0]
    assert tested_df_device["terc"].iloc[0] == tested_df_classes["terc"].iloc[0] == "2212011"

    id_import_value = tested_df_device["import_id"].iloc[0]
    terc_value = tested_df_device["terc"].iloc[0]

    expected_df_devices["import_id"] = id_import_value
    expected_df_devices["terc"] = terc_value
    expected_df_classes["import_id"] = id_import_value
    expected_df_classes["terc"] = terc_value
    expected_df_devices = expected_df_devices.reset_index().rename(columns={"index": "id"})
    expected_df_classes = expected_df_classes.reset_index().rename(columns={"index": "id"})
    pd.testing.assert_frame_equal(expected_df_devices, tested_df_device, check_like=True, check_dtype=False)
    pd.testing.assert_frame_equal(expected_df_classes, tested_df_classes, check_like=True, check_dtype=False)
