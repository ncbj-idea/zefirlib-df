import logging
from io import BytesIO
from unittest.mock import Mock

import pytest

from datafusion.configs.address_config import AddressConfig
from datafusion.readers.address_reader.wfs_client import AddressWfsClient

_CLIENT_MODULE = "datafusion.readers.address_reader.wfs_client"
_LAYER = "adresyUlice:A07_Punkty_adresowe"
_BBOX = (1.0, 2.0, 3.0, 4.0, "urn:ogc:def:crs:EPSG::2180")


def _make_page(number_returned: int, number_matched: int | str = "unknown") -> bytes:
    members = "<wfs:member><address/></wfs:member>" * number_returned
    return (
        '<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
        f'numberReturned="{number_returned}" numberMatched="{number_matched}">'
        f"{members}</wfs:FeatureCollection>"
    ).encode()


@pytest.fixture
def client() -> AddressWfsClient:
    return AddressWfsClient(
        AddressConfig(
            terc="0201011",
            url="https://mapy.geoportal.gov.pl/wss/ext/wfs/KrajowaIntegracjaNumeracjiAdresowej",
            layer_name=_LAYER,
            tmp_table_name="tmp_address_point_test",
            page_size=2,
        ),
        db_engine=Mock(),
    )


def _mock_wfs(monkeypatch: pytest.MonkeyPatch, pages: list[bytes]) -> Mock:
    wfs = Mock(url="https://example.com/wfs", contents={_LAYER: object()})
    wfs.getfeature.side_effect = [BytesIO(page) for page in pages]
    monkeypatch.setattr(f"{_CLIENT_MODULE}.WebFeatureService", lambda *args, **kwargs: wfs)
    monkeypatch.setattr(f"{_CLIENT_MODULE}.get_wfs_bbox_tuple", lambda *args: _BBOX)
    return wfs


@pytest.mark.parametrize(
    ("counts", "matched"),
    [([2, 1], 3), ([2, 2], 4), ([1], "unknown"), ([2, 0], "unknown")],
)
def test_fetch_data_pages_until_short_page_or_known_total(
    monkeypatch: pytest.MonkeyPatch, client: AddressWfsClient, counts: list[int], matched: int | str
) -> None:
    pages = [_make_page(count, matched) for count in counts]
    wfs = _mock_wfs(monkeypatch, pages)

    assert client.fetch_data() == pages
    assert wfs.getfeature.call_count == len(pages)
    offset = 0
    for call, count in zip(wfs.getfeature.call_args_list, counts):
        assert call.kwargs == {
            "typename": _LAYER,
            "srsname": "urn:ogc:def:crs:EPSG::2180",
            "bbox": _BBOX,
            "startindex": offset,
            "maxfeatures": 2,
        }
        offset += count


def test_fetch_data_warns_when_fewer_features_than_matched(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, client: AddressWfsClient
) -> None:
    _mock_wfs(monkeypatch, [_make_page(2, 4), _make_page(1, 4)])
    monkeypatch.setattr(logging.getLogger("datafusion"), "propagate", True)

    with caplog.at_level(logging.WARNING):
        client.fetch_data()

    assert "Fetched 3 of 4 matched features" in caplog.text


def test_fetch_data_requires_bbox(monkeypatch: pytest.MonkeyPatch, client: AddressWfsClient) -> None:
    wfs = _mock_wfs(monkeypatch, [])
    monkeypatch.setattr(f"{_CLIENT_MODULE}.get_wfs_bbox_tuple", lambda *args: None)

    with pytest.raises(RuntimeError, match="Fetching without a BBOX filter is not supported"):
        client.fetch_data()

    wfs.getfeature.assert_not_called()


def test_fetch_data_requires_configured_layer(monkeypatch: pytest.MonkeyPatch, client: AddressWfsClient) -> None:
    wfs = _mock_wfs(monkeypatch, [])
    wfs.contents = {"other_layer": object()}

    with pytest.raises(KeyError, match="Available layers.*other_layer"):
        client.fetch_data()

    wfs.getfeature.assert_not_called()


@pytest.mark.parametrize("content", [b"", b"short", b"not XML" * 30, b"<broken>" + b" " * 100])
def test_validate_response_rejects_invalid_xml(client: AddressWfsClient, content: bytes) -> None:
    with pytest.raises(ValueError, match="response"):
        client._validate_wfs_response(content)


def test_validate_response_rejects_exception_report(client: AddressWfsClient) -> None:
    content = b"<ExceptionReport><Exception>" + b"Error " * 30 + b"</Exception></ExceptionReport>"
    with pytest.raises(ValueError, match="Unexpected WFS response element: ExceptionReport"):
        client._validate_wfs_response(content)


def test_fetch_data_rejects_empty_first_page(monkeypatch: pytest.MonkeyPatch, client: AddressWfsClient) -> None:
    _mock_wfs(monkeypatch, [_make_page(0, 0)])

    with pytest.raises(ValueError, match="no address features"):
        client.fetch_data()


def test_validate_response_accepts_features_and_empty_later_pages(client: AddressWfsClient) -> None:
    client._validate_wfs_response(_make_page(1, 1))
    client._validate_wfs_response(_make_page(0), fail_on_empty=False)


@pytest.mark.parametrize("matched", [3, "unknown"])
def test_parse_collection_counts(client: AddressWfsClient, matched: int | str) -> None:
    assert client._parse_collection_counts(_make_page(2, matched)) == (2, 3 if matched == 3 else None)
