import logging

import numpy as np

from datafusion.kiut.layers import AllowedLayerNames
from datafusion.kiut.map_analyze.layer_checkers.interface import (
    ExistingLayers,
    LayerChecker,
)
from datafusion.utils.image.color import is_background

logger = logging.getLogger(__name__)


class CheckByNotBlankPixels(LayerChecker):
    """
    This funciton implements the algorithm of layers checking called check by not blank pixels.
    """

    def __init__(self, layer: AllowedLayerNames, grid_existence_threshold: float):
        self.grid_existence_threshold = grid_existence_threshold
        self.layer = layer

    def get_existing_layers(self, array: np.ndarray) -> ExistingLayers:
        """
        Gets existing layers according to the given array.
        Args:
            array (np.ndarray): Array to be checked.

        Returns:
            Retuns a list of existing layers.

        """
        grid_exist = ~self._get_blank_pixels(array)
        is_grid = np.sum(grid_exist) / grid_exist.size >= self.grid_existence_threshold
        return [self.layer] if is_grid else []

    @staticmethod
    def _get_blank_pixels(arr: np.ndarray) -> np.ndarray:
        """
        Gets blank pixels according to the given array.
        Args:
            arr: (np.ndarray): Array to be checked.

        Returns:
             np.ndarray: Array with boolean values representing blank pixels.

        """
        return is_background(arr)
