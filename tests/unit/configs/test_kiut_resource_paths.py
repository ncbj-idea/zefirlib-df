import json
from pathlib import Path
from xml.etree import ElementTree

import yaml


def test_default_kiut_configs_reference_existing_terc_xml():
    root = Path(__file__).resolve().parents[3]
    yaml_config = yaml.safe_load((root / "configs/data_sources/kiut.yml").read_text())
    json_config = json.loads((root / "datafusion_input/configs/kiut.json").read_text())

    for config in (yaml_config, json_config):
        xml_path = root / config["terc_urzedowy_xml_path"]
        assert xml_path.is_file()
        ElementTree.parse(xml_path)
