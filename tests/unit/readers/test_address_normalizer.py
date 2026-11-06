from unittest.mock import MagicMock

import pytest

from datafusion.readers.address_reader.normalizer import AddressNormalizer


def test_normalize_uses_new_wfs_property_names(monkeypatch: pytest.MonkeyPatch) -> None:
    context = MagicMock()
    db = context.__enter__.return_value
    monkeypatch.setattr("datafusion.readers.address_reader.normalizer.SessionContext", lambda *args: context)

    AddressNormalizer(db_engine=MagicMock()).normalize(import_id=42)

    sql, parameters = db.execute.call_args.args
    sql_text = str(sql)
    for key in ("nazwa_miejscowosci", "kod_pocztowy", "nazwa_ulicy", "numer_porzadkowy"):
        assert f"other ->> '{key}'" in sql_text
    for old_key in ("miejscowosc", "kod", "ulica", "numer"):
        assert f"other ->> '{old_key}'" not in sql_text
    assert "WHERE address_point.import_id = :import_id" in sql_text
    assert parameters == {"import_id": 42}
    db.commit.assert_called_once_with()
