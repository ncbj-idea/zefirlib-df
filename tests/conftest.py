import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from datafusion.configs.address_config import AddressConfig
from datafusion.configs.bdot_config import BDOTConfig
from datafusion.configs.borders_config import BordersConfig
from datafusion.configs.ceeb_config import CEEBConfig
from datafusion.configs.config import Config
from datafusion.configs.global_config import GlobalConfig
from datafusion.configs.kiut_config import KIUTConfig
from datafusion.configs.merge_config import MergeConfig
from datafusion.configs.postprocessing_config import PostprocessingConfig
from datafusion.configs.pvgis_config import PVGISConfig
from datafusion.database.db_settings import DBSettings
from tests.mock_configs import (
    ADDRESS_CONFIG,
    BDOT_CONFIG,
    BORDER_CONFIG,
    CEEB_CONFIG,
    GLOBAL_CONFIG,
    KIUT_CONFIG,
    MERGE_CONFIG,
    POSTPROCESSING_CONFIG,
    PVGIS_CONFIG,
)

logger = logging.getLogger(__name__)


def get_test_engine(mock_database_settings: DBSettings) -> Engine:
    return create_engine(mock_database_settings.connection_string)


@pytest.fixture
def test_session(mock_database_settings) -> Session:
    session_maker = sessionmaker(autocommit=False, autoflush=False, bind=get_test_engine(mock_database_settings))
    session = session_maker()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_config() -> Config:
    return Config(
        global_config=GlobalConfig(**GLOBAL_CONFIG),
        bdot=BDOTConfig(**BDOT_CONFIG),
        borders=BordersConfig(**BORDER_CONFIG),
        kiut=KIUTConfig(**KIUT_CONFIG),
        ceeb=CEEBConfig(**CEEB_CONFIG),
        address=AddressConfig(**ADDRESS_CONFIG),
        pvgis=PVGISConfig(**PVGIS_CONFIG),
        merge_config=MergeConfig(**MERGE_CONFIG),
        postprocessing=PostprocessingConfig(**POSTPROCESSING_CONFIG),
    )


@pytest.fixture
def mock_database_settings() -> DBSettings:
    return DBSettings()
