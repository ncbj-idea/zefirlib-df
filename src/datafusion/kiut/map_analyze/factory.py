import logging

from datafusion.configs.kiut_config import (
    PolygonizationMethodNames,
    PolygonizationMethodsConfig_T,
)
from datafusion.kiut.layers import AllowedLayerNames
from datafusion.kiut.map_analyze.layer_checkers.check_by_colors import CheckByLayerColor
from datafusion.kiut.map_analyze.layer_checkers.check_by_not_blank_pixels import (
    CheckByNotBlankPixels,
)
from datafusion.kiut.map_analyze.layer_checkers.interface import LayerChecker_T

logger = logging.getLogger(__name__)

GRID_EXISTENCE_THRESHOLD = 0.005


def get_grid_checker(layer_name: str, params: PolygonizationMethodsConfig_T) -> LayerChecker_T:
    """Factory for Polygonizer"""
    if params.name == PolygonizationMethodNames.NOT_BLANK_MAP.value:
        return CheckByNotBlankPixels(
            layer=AllowedLayerNames[layer_name],
            **params.dict(),
        )
    elif params.name == PolygonizationMethodNames.ANALYZE_COLORS_ON_MAP.value:
        return CheckByLayerColor(**params.dict())
    else:
        raise KeyError(f"Unexpected polygonization method {params.name}")
