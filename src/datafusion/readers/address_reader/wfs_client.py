"""
WFS Client for Address Reader.

This module provides the AddressWfsClient class for interacting with Geoportal WFS services.
"""

import logging

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

    def fetch_data(self) -> bytes:
        """
        Fetch address point data from WFS service.

        Returns:
            Raw GML content as bytes.

        Raises:
            KeyError: If the configured layer is not found.
            ValueError: If the response is invalid.
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
            "Sending WFS GetFeature request to %s (timeout: %s seconds)",
            wfs.url,
            self.config.timeout,
        )

        feature_params = self._prepare_wfs_feature_params()
        response = wfs.getfeature(**feature_params)
        _logger.debug("Received response from WFS service")

        response_content = response.read()
        _logger.debug("Response size: %d bytes", len(response_content))
        self._validate_wfs_response(response_content)

        return response_content

    def _prepare_wfs_feature_params(
        self,
    ) -> dict[str, str | tuple[float, float, float, float]]:
        """Prepare WFS GetFeature request parameters."""
        feature_params: dict[str, str | tuple[float, float, float, float]] = {
            "typename": self.config.layer_name,
            "startindex": 0,
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
            _logger.debug("No BBOX filter available - fetching all data from service")

        return feature_params

    def _validate_wfs_response(self, response_content: bytes) -> None:
        """Validate WFS response content."""
        if not response_content or len(response_content) < _MIN_RESPONSE_SIZE_BYTES:
            raise ValueError(
                f"Empty or invalid response received from WFS service. "
                f"Response size: {len(response_content) if response_content else 0} bytes. "
                f"Minimum expected size: {_MIN_RESPONSE_SIZE_BYTES} bytes"
            )
