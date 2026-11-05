"""
WFS Client for Address Reader.

This module provides the AddressWfsClient class for interacting with Geoportal WFS services.
"""

import logging
import xml.etree.ElementTree as ET
from typing import Any

from owslib.wfs import WebFeatureService
from sqlalchemy.engine import Engine

from datafusion.configs.address_config import AddressConfig
from datafusion.utils.spatial import get_wfs_bbox_tuple

_logger = logging.getLogger(__name__)

_MIN_RESPONSE_SIZE_BYTES = 100


class AddressWfsClient:
    """
    Client for interacting with Geoportal WFS service.
    """

    def __init__(self, config: AddressConfig, db_engine: Engine) -> None:
        self.config = config
        self.db_engine = db_engine

    def fetch_data(self) -> list[bytes]:
        """
        Fetch all address point pages using WFS 2.0 result paging.

        A single request can be truncated by the service's default page limit.

        Returns:
            List of raw GML FeatureCollection pages as bytes.

        Raises:
            KeyError: If the configured layer is not found.
            ValueError: If the response is invalid.
            RuntimeError: If no BBOX filter is available for the configured TERC.
        """
        _logger.info(
            "Starting fetch of address points from WFS service (version: %s)",
            self.config.wfs_version,
        )

        wfs = WebFeatureService(
            self.config.url,
            version=self.config.wfs_version,
            timeout=self.config.timeout,
        )
        assert wfs is not None
        _logger.debug("WFS connection established to %s", wfs.url)

        if self.config.layer_name not in wfs.contents:
            available_layers = list(wfs.contents.keys())
            _logger.error(
                "Layer '%s' not found in WFS service. Available layers: %s",
                self.config.layer_name,
                available_layers,
            )
            raise KeyError(
                f"Layer '{self.config.layer_name}' not found in WFS service. Available layers: {available_layers}"
            )

        _logger.info(
            "Sending WFS GetFeature requests to %s (timeout: %s seconds, page size: %s)",
            wfs.url,
            self.config.timeout,
            self.config.page_size,
        )

        feature_params = self._prepare_wfs_feature_params()
        return self._fetch_all_pages(wfs, feature_params)

    def _fetch_all_pages(
        self,
        wfs: Any,
        feature_params: dict[str, str | int | tuple[float, float, float, float, str]],
    ) -> list[bytes]:
        """Fetch pages until a short page or the known total is reached."""
        pages: list[bytes] = []
        total_returned = 0
        number_matched: int | None = None
        startindex = 0

        while True:
            request_params = {**feature_params, "startindex": startindex, "maxfeatures": self.config.page_size}
            response = wfs.getfeature(**request_params)
            response_content = response.read()
            _logger.debug("Response size at startindex=%d: %d bytes", startindex, len(response_content))
            self._validate_wfs_response(response_content, fail_on_empty=startindex == 0)

            number_returned, page_number_matched = self._parse_collection_counts(response_content)
            if number_matched is None and page_number_matched is not None:
                number_matched = page_number_matched

            pages.append(response_content)
            total_returned += number_returned
            _logger.info(
                "Fetched page %d: %d features (startindex=%d, numberMatched=%s)",
                len(pages),
                number_returned,
                startindex,
                number_matched if number_matched is not None else "unknown",
            )

            if number_returned < self.config.page_size:
                break
            if number_matched is not None and startindex + number_returned >= number_matched:
                break
            startindex += number_returned

        if number_matched is not None and total_returned < number_matched:
            _logger.warning(
                "Fetched %d of %d matched features for TERC %s. "
                "The data set may have changed during paging (PagingIsTransactionSafe=FALSE).",
                total_returned,
                number_matched,
                self.config.terc,
            )

        _logger.info(
            "Fetched %d features in %d page(s) for TERC %s",
            total_returned,
            len(pages),
            self.config.terc,
        )
        return pages

    @staticmethod
    def _parse_collection_counts(response_content: bytes) -> tuple[int, int | None]:
        """Read numberReturned and numberMatched (None when unknown/absent)."""
        root = ET.fromstring(response_content)
        number_returned = root.get("numberReturned")
        number_matched = root.get("numberMatched")
        return (
            int(number_returned) if number_returned is not None else 0,
            int(number_matched) if number_matched is not None and number_matched.isdigit() else None,
        )

    def _prepare_wfs_feature_params(
        self,
    ) -> dict[str, str | int | tuple[float, float, float, float, str]]:
        """Prepare WFS GetFeature request parameters without paging params."""
        feature_params: dict[str, str | int | tuple[float, float, float, float, str]] = {
            "typename": self.config.layer_name,
            "srsname": f"urn:ogc:def:crs:EPSG::{self.config.srid}",
        }

        bbox_tuple = get_wfs_bbox_tuple(self.db_engine, self.config.terc, self.config.srid)
        if bbox_tuple:
            feature_params["bbox"] = bbox_tuple
            bbox_string = f"{bbox_tuple[0]},{bbox_tuple[1]},{bbox_tuple[2]},{bbox_tuple[3]},EPSG:{self.config.srid}"
            _logger.info(
                "Applying BBOX filter for TERC %s: %s",
                self.config.terc,
                bbox_string,
            )
        else:
            raise RuntimeError(
                f"No administrative boundary found for TERC {self.config.terc} (srid {self.config.srid}). "
                "Import borders first (borders runner) or verify the TERC code. "
                "Fetching without a BBOX filter is not supported."
            )

        return feature_params

    def _validate_wfs_response(self, response_content: bytes, fail_on_empty: bool = True) -> None:
        """Validate XML and reject empty first pages; later empty pages may terminate paging."""
        if not response_content or len(response_content) < _MIN_RESPONSE_SIZE_BYTES:
            raise ValueError(
                f"Empty or invalid response received from WFS service. "
                f"Response size: {len(response_content) if response_content else 0} bytes. "
                f"Minimum expected size: {_MIN_RESPONSE_SIZE_BYTES} bytes"
            )

        try:
            root = ET.fromstring(response_content)
        except ET.ParseError as e:
            raise ValueError("Invalid XML response received from WFS service") from e

        root_name = root.tag.rsplit("}", 1)[-1]
        if root_name != "FeatureCollection":
            raise ValueError(f"Unexpected WFS response element: {root_name}")

        number_returned = root.get("numberReturned")
        if fail_on_empty and number_returned is not None and int(number_returned) == 0:
            raise ValueError(f"WFS response contains no address features for TERC {self.config.terc}")
