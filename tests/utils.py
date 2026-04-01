from pathlib import Path
from xml.etree.ElementTree import Element

_ROOT_DIR = Path(__file__).parent.parent

_RESOURCES_PATH = Path(__file__).parent / "resources"
_ALEMBIC_PATH = _ROOT_DIR / "alembic.ini"


def get_resources(x: str | None) -> Path:
    if x is not None:
        return _RESOURCES_PATH / Path(x)
    return _RESOURCES_PATH


def get_alembic_path() -> Path:
    return _ALEMBIC_PATH


def compare_xmls(xml1: Element, xml2: Element, child_num: int = 5) -> bool:
    valid: bool = True
    if xml1.tag != xml2.tag:
        valid = False
    if xml1.attrib != xml2.attrib:
        valid = False
    if (xml1.text or "").strip() != (xml2.text or "").strip():
        valid = False
    if (xml1.tail or "").strip() != (xml2.tail or "").strip():
        valid = False
    if len(list(xml1)) != len(list(xml2)):
        valid = False
    for child1, child2 in zip(list(xml1)[:child_num], list(xml2)[:child_num]):
        if not compare_xmls(child1, child2):
            valid = False
    return valid
