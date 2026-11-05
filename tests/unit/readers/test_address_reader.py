from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from datafusion.configs.address_config import AddressConfig
from datafusion.configs.borders_config import BordersConfig
from datafusion.database.db_settings import DBSettings
from datafusion.readers.address_reader import AddressReader
from datafusion.utils.spatial import BBOX, get_wfs_bbox
from tests.conftest import get_test_engine
from tests.mock_configs import BORDER_CONFIG


def test_address_reader_instantiation(mock_database_settings: DBSettings):
    """Test that AddressReader can be instantiated with valid config."""
    address_config = AddressConfig(
        terc="0201011",
        url="https://mapy.geoportal.gov.pl/wss/ext/wfs/KrajowaIntegracjaNumeracjiAdresowej",
        layer_name="adresyUlice:A07_Punkty_adresowe",
        tmp_table_name="tmp_address_point_test",
        tmp_table_schema="tmp",
        geometry_column_name="geometria",
    )
    engine = get_test_engine(mock_database_settings)

    reader = AddressReader(config=address_config, db_engine=engine, db_settings=mock_database_settings)

    assert isinstance(reader, AddressReader)
    assert reader.config == address_config
    assert reader.db_engine == engine
    assert reader.db_settings == mock_database_settings


def test_address_config_bbox_generation(mock_database_settings: DBSettings):
    """Test BBOX generation from administrative boundary data."""
    address_config = AddressConfig(
        terc="0201011",
        url="https://mapy.geoportal.gov.pl/wss/ext/wfs/KrajowaIntegracjaNumeracjiAdresowej",
        layer_name="adresyUlice:A07_Punkty_adresowe",
        tmp_table_name="tmp_address_point_test",
        tmp_table_schema="tmp",
        geometry_column_name="geometria",
    )
    engine = get_test_engine(mock_database_settings)

    # Test BBOX generation using new spatial.get_wfs_bbox
    bbox = get_wfs_bbox(engine, address_config.terc)

    # BBOX should be None if no administrative boundary data exists
    # In a real scenario with boundary data, this would return a BBOX object
    assert bbox is None or isinstance(bbox, BBOX)

    if bbox:
        # Verify BBOX object has correct attributes
        assert hasattr(bbox, "minx")
        assert hasattr(bbox, "miny")
        assert hasattr(bbox, "maxx")
        assert hasattr(bbox, "maxy")
        assert hasattr(bbox, "srid")

        # Verify BBOX string format: "minx,miny,maxx,maxy,srsname"
        bbox_string = bbox.to_string()
        coords = bbox_string.split(",")
        assert len(coords) == 5
        # First 4 coordinates should be numeric
        for coord in coords[:4]:
            assert coord.replace(".", "", 1).replace("-", "", 1).isdigit()
        # Last coordinate should be the SRS name
        assert coords[4].startswith("urn:ogc:def:crs:EPSG::")

        # Verify BBOX tuple format for OWSLib: (minx, miny, maxx, maxy, srsname)
        bbox_tuple = bbox.to_tuple()
        assert len(bbox_tuple) == 5
        assert isinstance(bbox_tuple[0], float)  # minx
        assert isinstance(bbox_tuple[1], float)  # miny
        assert isinstance(bbox_tuple[2], float)  # maxx
        assert isinstance(bbox_tuple[3], float)  # maxy
        assert isinstance(bbox_tuple[4], str)  # srsname


@pytest.fixture
def reader(mock_database_settings: DBSettings) -> AddressReader:
    config = AddressConfig(
        terc="0201011",
        url="https://mapy.geoportal.gov.pl/wss/ext/wfs/KrajowaIntegracjaNumeracjiAdresowej",
        layer_name="adresyUlice:A07_Punkty_adresowe",
        tmp_table_name="tmp_address_point_test",
    )
    return AddressReader(
        config,
        get_test_engine(mock_database_settings),
        mock_database_settings,
        borders_config=BordersConfig(**{**BORDER_CONFIG, "terc": config.terc}),
    )


def test_existing_boundary_skips_border_import(monkeypatch: pytest.MonkeyPatch, reader: AddressReader) -> None:
    borders = Mock()
    monkeypatch.setattr("datafusion.readers.address_reader.address_reader.BordersReader", borders)
    monkeypatch.setattr("datafusion.readers.address_reader.address_reader.get_wfs_bbox", lambda *args: object())

    reader._ensure_administrative_boundary()

    borders.assert_not_called()


@pytest.mark.parametrize("import_succeeds", [True, False])
def test_missing_boundary_triggers_import_and_recheck(
    monkeypatch: pytest.MonkeyPatch, reader: AddressReader, import_succeeds: bool
) -> None:
    borders = Mock()
    bbox = Mock(side_effect=[None, object() if import_succeeds else None])
    monkeypatch.setattr("datafusion.readers.address_reader.address_reader.BordersReader", borders)
    monkeypatch.setattr("datafusion.readers.address_reader.address_reader.get_wfs_bbox", bbox)

    if import_succeeds:
        reader._ensure_administrative_boundary()
    else:
        with pytest.raises(RuntimeError, match="produced no administrative boundary"):
            reader._ensure_administrative_boundary()

    assert bbox.call_count == 2
    borders.assert_called_once_with(
        config=reader.borders_config, db_settings=reader.db_settings, engine=reader.db_engine
    )
    borders.return_value.run.assert_called_once_with()


def test_missing_boundary_without_border_config_fails_safely(
    monkeypatch: pytest.MonkeyPatch, reader: AddressReader
) -> None:
    reader.borders_config = None
    monkeypatch.setattr("datafusion.readers.address_reader.address_reader.get_wfs_bbox", lambda *args: None)

    with pytest.raises(RuntimeError, match="Import borders first"):
        reader._ensure_administrative_boundary()


def test_staging_replaces_first_page_then_appends(monkeypatch: pytest.MonkeyPatch, reader: AddressReader) -> None:
    ogr = Mock()
    pages = [b"first page", b"second page", b"third page"]
    imported_contents = []
    imported_paths = []

    def capture_page(file, db_settings):
        imported_contents.append(file.read_bytes())
        imported_paths.append(file)
        assert db_settings == reader.db_settings

    ogr.return_value.side_effect = capture_page
    monkeypatch.setattr("datafusion.readers.address_reader.address_reader.OgrCaller", ogr)

    reader._import_gml_pages_to_staging_table(pages)

    assert imported_contents == pages
    assert [path.name for path in imported_paths] == [f"address_points_page_{i:03d}.gml" for i in range(1, 4)]
    assert all(not path.exists() for path in imported_paths)
    assert [call.kwargs["replace"] for call in ogr.call_args_list] == [True, False, False]
    for call in ogr.call_args_list:
        assert call.kwargs["table_name"] == "tmp.tmp_address_point_test"
        assert call.kwargs["layer_name"] == reader.config.layer_name
        assert call.kwargs["use_layer_name"] is False


@pytest.mark.parametrize("row_count", [0, 3])
def test_import_checks_boundary_and_insert_count_before_commit(
    monkeypatch: pytest.MonkeyPatch, reader: AddressReader, row_count: int
) -> None:
    context = MagicMock()
    db = context.__enter__.return_value
    db.query.return_value.filter.return_value.count.return_value = row_count
    monkeypatch.setattr("datafusion.readers.address_reader.address_reader.SessionContext", lambda *args: context)
    monkeypatch.setattr("datafusion.readers.address_reader.address_reader.Table", Mock())
    monkeypatch.setattr(reader, "get_meta_obj", Mock(return_value=SimpleNamespace(id=42)))
    events = []
    monkeypatch.setattr(reader, "_ensure_administrative_boundary", lambda: events.append("boundary"))
    pages = [b"page 1", b"page 2"]
    reader.wfs_client.fetch_data = Mock(side_effect=lambda: events.append("fetch") or pages)
    staging = Mock()
    monkeypatch.setattr(reader, "_import_gml_pages_to_staging_table", staging)
    reader.repository = Mock()

    if row_count:
        assert reader._import_address_data_to_db(remove_staging_table=False) == 42
        db.commit.assert_called_once_with()
        db.rollback.assert_not_called()
    else:
        with pytest.raises(RuntimeError, match="No address points were imported"):
            reader._import_address_data_to_db(remove_staging_table=False)
        db.commit.assert_not_called()
        db.rollback.assert_called_once_with()

    assert events == ["boundary", "fetch"]
    staging.assert_called_once_with(pages)
    assert reader.repository.append_from_staging.call_args.kwargs["geometry_column_name"] == "geometria"
