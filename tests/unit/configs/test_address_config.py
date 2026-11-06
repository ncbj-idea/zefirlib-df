from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from datafusion.configs.address_config import AddressConfig


def _config_values() -> dict:
    config_path = Path(__file__).resolve().parents[3] / "configs/data_sources/address.yml"
    return {"terc": "0201011", **yaml.safe_load(config_path.read_text())}


def test_default_address_config_matches_new_wfs_service() -> None:
    config = AddressConfig(**_config_values())
    assert config.url == "https://mapy.geoportal.gov.pl/wss/ext/wfs/KrajowaIntegracjaNumeracjiAdresowej"
    assert config.layer_name == "adresyUlice:A07_Punkty_adresowe"
    assert config.geometry_column_name == "geometria"
    assert config.page_size == 10000
    assert config.teryt == "02"


def test_address_config_defaults() -> None:
    values = _config_values()
    for key in ("tmp_table_schema", "geometry_column_name", "page_size"):
        values.pop(key)
    config = AddressConfig(**values)
    assert config.tmp_table_schema == "tmp"
    assert config.geometry_column_name == "geometria"
    assert config.page_size == 10000


@pytest.mark.parametrize("page_size", [0, -1])
def test_address_page_size_must_be_positive(page_size: int) -> None:
    values = {**_config_values(), "page_size": page_size}
    with pytest.raises(ValidationError):
        AddressConfig(**values)
