import pytest

# from io import BytesIO
#
# # from tempfile import TemporaryDirectory
# from zipfile import ZipFile
#
# import pandas as pd
# ```
# import requests
# from sqlalchemy import select
from sqlalchemy.orm import Session

#
# from datafusion.configs.bdot_config import BDOTConfig
from datafusion.configs.config import Config
from datafusion.database.db_settings import DBSettings

# from datafusion.database.models.bdot import BDOT
# from datafusion.readers.bdot_reader import BDOTReader
# from tests.conftest import get_test_engine
# from tests.mock_configs import BDOT_CONFIG, BDOT_MOCK_MAPPER, ResourcesSubDirectory
# from tests.utils import get_resources


@pytest.mark.skip("We are not using osgeo ogr need to reimplement this test")
def test_run(
    test_session: Session,
    mock_config: Config,
    mock_database_settings: DBSettings,
) -> None:
    pass
    # TODO: refactor this test, as we are using bash call to ogr2ogr now
    # test_engine = get_test_engine(mock_database_settings)
    # bdot_reader = BDOTReader(
    #     config=BDOTConfig(**BDOT_CONFIG),
    #     session=test_session,
    #     engine=test_engine,
    #     db_settings=mock_database_settings,
    # )
    # bdot_reader.run()
    #
    # expected_common_columns = [
    #     "funkcja_ogolna",
    #     "funkcja_szczegolowa",
    #     "liczba_kondygnacji",
    #     "kst",
    #     "czy_zabytek",
    # ]
    #
    # with test_engine.connect() as conn:
    #     tested_df = pd.read_sql(sql=str(select(BDOT)), con=conn)
    # tested_df = tested_df[expected_common_columns]
    #
    # mapper = mock_config.bdot._get_map_from_json(
    #     get_resources(f"{ResourcesSubDirectory.BDOT}/{BDOT_MOCK_MAPPER}")
    # )
    #
    # response = requests.get(mock_config.bdot.url)
    # content = BytesIO(response.content)
    # with ZipFile(content) as _zip:
    #     building_xmls = [
    #         file
    #         for file in _zip.infolist()
    #         if mock_config.bdot.layer_name in file.filename
    #     ]
    #     if len(building_xmls) == 1:
    #         building_xml = building_xmls[0]
    #     with TemporaryDirectory() as tmp_dir:
    #         filepath = _zip.extract(building_xml.filename, path=tmp_dir)
    #         driver = ogr.GetDriverByName("GML")
    #         datasource = driver.Open(filepath, 0)
    #         layer = datasource.GetLayer()
    #         layer_defn = layer.GetLayerDefn()
    #         field_names = [
    #             layer_defn.GetFieldDefn(i).GetName()
    #             for i in range(layer_defn.GetFieldCount())
    #         ]
    #         data = []
    #         for feature in layer:
    #             feature_data = {}
    #             for field in field_names:
    #                 feature_data[field] = feature.GetField(field)
    #             geom = feature.GetGeometryRef()
    #             if geom:
    #                 feature_data["geometry"] = geom.ExportToWkt()
    #             else:
    #                 feature_data["geometry"] = None
    #             data.append(feature_data)
    #
    #         expected_df = pd.DataFrame(data)
    # expected_df.columns = map(str.lower, expected_df.columns)
    # expected_df.rename(columns=mapper, inplace=True)
    # expected_df = expected_df[expected_common_columns]
    #
    # assert expected_df.shape == tested_df.shape
