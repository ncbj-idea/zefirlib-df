from abc import abstractmethod
from enum import StrEnum

from pydantic import BaseModel

from datafusion.constants import BACKGROUND_RGBA, POLAND_CS92_SRID
from datafusion.utils.typings import RGBA_T

KIUT_URL = "https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaUzbrojeniaTerenu"


class PolygonizationMethodNames(StrEnum):
    NOT_BLANK_MAP = "NOT_BLANK_MAP"
    ANALYZE_COLORS_ON_MAP = "ANALYZE_COLORS_ON_MAP"


class IPolygonizationMethodConfig(BaseModel):
    grid_existence_threshold: float = 0.005

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError


class NotBlankMapConfig(IPolygonizationMethodConfig):
    @property
    def name(self) -> str:
        return str(PolygonizationMethodNames.NOT_BLANK_MAP.value)


class AnalyzeColorsOnMapConfig(IPolygonizationMethodConfig):
    background_rgba: RGBA_T = BACKGROUND_RGBA
    # layer_colors: dict[AllowedLayerNames, RGBA_T] = LAYERS_COLORS

    @property
    def name(self) -> str:
        return str(PolygonizationMethodNames.ANALYZE_COLORS_ON_MAP.value)


PolygonizationMethodsConfig_T = NotBlankMapConfig | AnalyzeColorsOnMapConfig


class WMSConfig(BaseModel):
    bbox_size: int = 1000
    image_size: int = 1000
    max_connections: int = 3
    url: str = KIUT_URL
    version: str = "1.3.0"
    srid: int = POLAND_CS92_SRID  # ask server for this srid


class KIUTConfig(BaseModel):
    terc_urzedowy_xml_path: str
    terc: str
    layers: list[str]
    polygonization: PolygonizationMethodsConfig_T
    wms: WMSConfig
    number_of_slices_of_image_side: int
