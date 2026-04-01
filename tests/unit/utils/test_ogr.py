from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pytest

from datafusion.configs.config import Config
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import create_schema_if_not_exists
from datafusion.readers.bdot_reader import BDOTReader
from datafusion.utils.ogr import OgrCaller
from tests.conftest import get_test_engine

_EXPECTED_COLUMNS: list[str] = [
    "ogc_fid",
    "gml_id",
    "lokalnyid",
    "przestrzennazw",
    "wersjaid",
    "czyobiektbdoo",
    "x_kod",
    "x_skrkarto",
    "x_katdoklgeom",
    "x_zrodlodanychg",
    "x_zrodlodanycha",
    "x_katistnienia",
    "x_rodzajreprgeom",
    "x_aktualnoscg",
    "x_aktualnosca",
    "poczatekwersjiobiektu",
    "x_datautworzenia",
    "x_kodkarto10k",
    "x_kodkarto25k",
    "x_kodkarto50k",
    "x_kodkarto100k",
    "x_kodkarto250k",
    "x_kodkarto500k",
    "x_kodkarto1000k",
    "funogolnabudynku",
    "funszczegolowabudynku",
    "liczbakondygnacji",
    "kodkst",
    "zabytek",
    "egib|bt_referencjadoobiektu|idiip|bt_identyfikator|lokalnyid",
    "egib|bt_referencjadoobiektu|idiip|bt_identyfikator|prz_af18461e",
    "egib|bt_referencjadoobiektu|idiip|bt_identyfikator|przestrzenna",
    "x_informdodatkowa",
    "nazwa",
    "x_uwagi",
    "geometria",
]
_EXPECTED_N_ROWS: int = 40009


@pytest.fixture
def ogr(mock_config: Config) -> OgrCaller:
    table_name = f"{mock_config.bdot.tmp_table_schema}.{mock_config.bdot.tmp_table_name}"
    return OgrCaller(
        table_name=table_name,
        layer_name=mock_config.bdot.layer_name,
        layer_type="PROMOTE_TO_MULTI",
    )


def test_ogr_caller(
    mock_config: Config,
    bdot_reader: BDOTReader,
    ogr: OgrCaller,
    mock_database_settings: DBSettings,
) -> None:
    test_engine = get_test_engine(mock_database_settings)
    with TemporaryDirectory() as tmp_dir:
        content = BytesIO(bdot_reader.read(bdot_reader.config.url))
        layer = bdot_reader._fetch_layer(content, Path(tmp_dir))
        create_schema_if_not_exists(mock_config.bdot.tmp_table_schema, test_engine)
        ogr(layer, mock_database_settings)

    with test_engine.connect() as conn:
        df = pd.read_sql_table(
            table_name=mock_config.bdot.tmp_table_name,
            con=conn,
            schema=mock_config.bdot.tmp_table_schema,
        )
    assert not [col for col in df.columns if col not in _EXPECTED_COLUMNS]
    assert df.shape[0] == _EXPECTED_N_ROWS
