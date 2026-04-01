import pytest
from sqlalchemy.orm import Session

from datafusion.configs.kiut_config import KIUTConfig
from datafusion.database.db_settings import DBSettings
from datafusion.database.initialize import initialize_kiut_util_database
from datafusion.readers.kiut_reader import KIUTReader
from datafusion.utils.setup_logging import setup_logging
from tests.conftest import get_test_engine

setup_logging()


@pytest.mark.skip
def test_kiut_reader(test_session: Session, mock_database_settings: DBSettings) -> None:
    config = KIUTConfig()
    engine = get_test_engine(mock_database_settings)
    initialize_kiut_util_database(test_session)
    kiut_reader = KIUTReader(config=config, session=test_session, engine=engine)
    kiut_reader.run()
