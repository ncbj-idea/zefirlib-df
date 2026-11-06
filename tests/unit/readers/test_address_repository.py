from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from datafusion.readers.address_reader.repository import AddressRepository


@pytest.mark.parametrize("rowcount", [0, 2])
def test_append_from_staging_rejects_only_zero_inserted_rows(monkeypatch: pytest.MonkeyPatch, rowcount: int) -> None:
    statement = object()
    monkeypatch.setattr("datafusion.readers.address_reader.repository.build_insert", lambda *args: statement)
    db = Mock()
    db.execute.return_value = SimpleNamespace(rowcount=rowcount)
    raw_table = Mock()
    raw_table.columns = []
    repository = AddressRepository()

    if rowcount == 0:
        with pytest.raises(ValueError, match="No address points inserted"):
            repository.append_from_staging(db, 42, raw_table, "geometria")
    else:
        repository.append_from_staging(db, 42, raw_table, "geometria")

    db.execute.assert_called_once_with(statement, {"import_id": 42})
