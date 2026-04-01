import xml.etree.ElementTree as ET
from pathlib import Path

from sqlalchemy.orm.session import Session

from datafusion.database.models.terc import Terc


def import_terc_codes(db: Session, teryt_urzedowy_path: Path) -> None:
    """
    https://eteryt.stat.gov.pl/eTeryt/rejestr_teryt/udostepnianie_danych/baza_teryt/uzytkownicy_indywidualni/pobieranie/pliki_pelne.aspx?contrast=default
    """
    tree = ET.parse(teryt_urzedowy_path)
    root = tree.getroot()
    mappings = []
    for row in root.find("catalog"):
        elements = {el.tag: el.text for el in row}
        teryt = "".join(elements[code] if elements[code] is not None else "" for code in ["WOJ", "POW", "GMI", "RODZ"])
        mappings.append(
            {
                "kod": teryt,
                "woj": elements["WOJ"],
                "pow": elements["POW"],
                "gmi": elements["GMI"],
                "rodz": elements["RODZ"],
                "nazwa": elements["NAZWA"],
                "nazwa_dod": elements["NAZWA_DOD"],
            }
        )
    db.bulk_insert_mappings(Terc, mappings)
    db.commit()
