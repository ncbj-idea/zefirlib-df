import pytest

from datafusion.configs.bdot_config import BDOTConfig
from datafusion.database.db_settings import DBSettings
from datafusion.readers.bdot_reader import BDOTReader
from tests.conftest import get_test_engine
from tests.mock_configs import BDOT_CONFIG


@pytest.fixture
def bdot_reader(
    mock_database_settings: DBSettings,
) -> BDOTReader:
    return BDOTReader(
        config=BDOTConfig(**BDOT_CONFIG),
        engine=get_test_engine(mock_database_settings),
        db_settings=mock_database_settings,
    )
