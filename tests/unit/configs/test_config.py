from pathlib import Path

import pydantic
import pytest

from datafusion.configs.bdot_config import BDOTConfig
from datafusion.configs.borders_config import BordersConfig
from datafusion.configs.ceeb_config import CEEBConfig
from datafusion.configs.config import Config, ConfigError
from datafusion.configs.kiut_config import (
    AnalyzeColorsOnMapConfig,
    KIUTConfig,
    WMSConfig,
)
from datafusion.configs.pvgis_config import PVGISConfig
from tests.mock_configs import (
    BDOT_CONFIG,
    BORDER_CONFIG,
    CEEB_CONFIG,
    CEEB_DEVICES_MOCK_FILE,
    KIUT_CONFIG,
    PVGIS_CONFIG,
    ResourcesSubDirectory,
)
from tests.utils import get_resources


def test_config_manager(mock_config: Config):
    assert isinstance(mock_config, Config)
    assert mock_config.bdot == BDOTConfig(**BDOT_CONFIG)
    assert mock_config.borders == BordersConfig(**BORDER_CONFIG)
    assert mock_config.kiut == KIUTConfig(**KIUT_CONFIG)
    assert mock_config.ceeb == CEEBConfig(**CEEB_CONFIG)
    assert mock_config.pvgis == PVGISConfig(**PVGIS_CONFIG)


def test_invalid_config():
    with pytest.raises(pydantic.ValidationError):
        Config(
            bdot=BDOTConfig(
                url="dummy_url",
                nr_powiatu=222,  # INVALID FIELD IS HERE !!!
                nr_wojewodztwa="9999",
                layer_name="dummy_layer_name",
                tmp_table_name="dummy_table_name",
                tmp_table_schema="dummy_table_schema",
                geom_col_name="dummy_geom_col_name",
                source_column_map={"dummy_key": "dummy_value"},
            ),
            ceeb=CEEBConfig(
                file_path=str(get_resources(f"{ResourcesSubDirectory.CEEB}/{CEEB_DEVICES_MOCK_FILE}")),
                tmp_table_schema="tmp",
            ),
            borders=BordersConfig(
                url="https://mapy.geoportal.gov.pl/wss/service/PZGIK/PRG/WFS/AdministrativeBoundaries",
                layer_name="A05_Granice_jednostek_ewidencyjnych",
                tmp_table_name="tmp_administative_boundaries",
                wfs_version="1.1.0",
                timeout="600",
                tmp_table_schema="tmp",
            ),
            kiut=KIUTConfig(
                terc_urzedowy_xml_path=get_resources("kiut/TERC_Urzedowy"),
                terc="2212011",
                layers=["przewod_cieplowniczy", "przewod_gazowy"],
                polygonization=AnalyzeColorsOnMapConfig(grid_existence_threshold=0.005, background_rgba=(0, 0, 0, 0)),
                wms=WMSConfig(
                    bbox_size=500,
                    image_size=1000,
                    url="https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaUzbrojeniaTerenu",
                    version="1.3.0",
                    srid=2180,
                ),
                number_of_slices_of_image_side=50,
            ),
        )


@pytest.mark.parametrize(
    "path, expected_exception, expected_exception_msg,",
    [
        pytest.param(
            Path(__file__),
            ConfigError,
            f"File: {Path(__file__)} does not exist or it is not in expected extensions: ['.json', '.yml', '.yaml']",
            id="invalid extension",
        ),
    ],
)
def test_from_config_yml_path(path: Path, expected_exception, expected_exception_msg: str) -> None:
    with pytest.raises(expected_exception) as e_info:
        Config.from_file(path)
    assert str(e_info.value) == expected_exception_msg
