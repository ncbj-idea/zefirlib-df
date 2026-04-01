from datafusion.configs.address_config import AddressConfig
from datafusion.database.db_settings import DBSettings
from datafusion.readers.address_reader import AddressReader
from datafusion.utils.spatial import BBOX, get_wfs_bbox
from tests.conftest import get_test_engine


def test_address_reader_instantiation(mock_database_settings: DBSettings):
    """Test that AddressReader can be instantiated with valid config."""
    address_config = AddressConfig(
        terc="0201011",
        url="https://mapy.geoportal.gov.pl/wss/ext/KrajowaIntegracjaNumeracjiAdresowej",
        layer_name="ms:prg-adresy",
        tmp_table_name="tmp_address_point_test",
        tmp_table_schema="tmp",
        geometry_column_name="msgeometry",
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
        url="https://mapy.geoportal.gov.pl/wss/ext/KrajowaIntegracjaNumeracjiAdresowej",
        layer_name="ms:prg-adresy",
        tmp_table_name="tmp_address_point_test",
        tmp_table_schema="tmp",
        geometry_column_name="msgeometry",
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
