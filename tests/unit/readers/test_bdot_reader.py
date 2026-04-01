import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from datafusion.readers.bdot_reader import BDOTReader
from tests.utils import compare_xmls


def test_bdot_fetch_layer(bdot_reader: BDOTReader) -> None:
    with TemporaryDirectory() as tmp_dir:
        content = BytesIO(bdot_reader.read(bdot_reader.config.url))

        tested_layer = bdot_reader._fetch_layer(content, tmp_dir)
        tested_layer = tested_layer.rename(tested_layer.parent / "tested_xml.xml")

        with ZipFile(content) as _zip:
            building_xmls = [file for file in _zip.infolist() if bdot_reader.config.layer_name in file.filename]
            if len(building_xmls) == 1:
                building_xml = building_xmls[0]
            filepath = _zip.extract(building_xml.filename, path=tmp_dir)
        expected_layer = Path(filepath)

        tree1 = ET.parse(tested_layer)
        tree2 = ET.parse(expected_layer)

        root1 = tree1.getroot()
        root2 = tree2.getroot()
        compare_xmls(root1, root2, 3)
