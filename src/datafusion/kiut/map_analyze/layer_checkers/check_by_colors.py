import logging

import numpy as np

from datafusion.constants import BACKGROUND_RGBA
from datafusion.kiut.layers import LAYERS_COLORS, LayerNames
from datafusion.kiut.map_analyze.layer_checkers.interface import (
    ExistingLayers,
    LayerChecker,
)
from datafusion.utils.image.normalization import normalize_rgba_array
from datafusion.utils.typings import RGBA_T

logger = logging.getLogger(__name__)


class CheckByLayerColorError(Exception):
    """
    Exception for CheckByLayerColors
    """

    pass


class CheckByLayerColor(LayerChecker):
    """
    Class for implementing algotithm of checking the layer color from the image data.
    """

    def __init__(
        self,
        layer_colors: dict[LayerNames, RGBA_T] | None = None,
        grid_existence_threshold: float = 0,
        max_error: np.uint8 | None = None,
        background_rgba: RGBA_T = BACKGROUND_RGBA,
    ):
        """

        Args:
            layer_colors (dict[LayerNames, RGBA_T]): Dictionary of layer names to RGBA color definition
            grid_existence_threshold (float): Threshold to determine if a layer exists
            max_error (np.uint8): Maximum error value to check
            background_rgba (RGBA_T): Background RGBA image
        """
        if not layer_colors:
            layer_colors = LAYERS_COLORS
        self.layer_colors = layer_colors
        self.grid_existence_threshold = grid_existence_threshold
        self.max_error = max_error
        self.background_rgba = background_rgba

    def get_existing_layers(self, array: np.ndarray) -> ExistingLayers:
        """
        This function gets the existing layers from a numpy array
        Args:
            array (np.ndarray): Numpy array with input RGBA data

        Returns:
            existing_layers (ExistingLayers): Existing layers

        """
        normarr = normalize_rgba_array(
            arr=array,
            layer_to_color=self.layer_colors,
            max_error=self.max_error,
            background_rgba=self.background_rgba,
        )
        grid_existence = self._get_layer_existence_indicator(normarr)
        return [layer for layer, exist in grid_existence.items() if exist]

    def _get_layer_existence_indicator(self, arr: np.ndarray) -> dict[str, bool]:
        """
        THis function is used to determine if a layer exists
        Args:
            arr(np.ndarray): Numpy array with input RGBA data

        Returns:
            Returns dictionary maping layer name to bool variable representing existence of given layer
        """
        height, width, _ = arr.shape
        grid_size = self._count_pixels_in_layers(arr)
        if not (self._get_number_of_blank_pixels(arr) + sum(grid_size.values()) == height * width):
            total = self._get_number_of_blank_pixels(arr) + sum(grid_size.values())
            raise CheckByLayerColorError(
                f"Total of blank pixels and grid size should equal {height * width},but it is {total}"
            )

        grid_existence = {}
        for layer, count_of_pixels in grid_size.items():
            grid_existence[layer] = count_of_pixels / (height * width) >= self.grid_existence_threshold
        return grid_existence

    def _count_pixels_in_layers(self, arr: np.ndarray) -> dict[str, int]:
        """
        This funciton counts pixels in giver layer
        Args:
            arr: Numpy array with input RGBA data

        Returns:
            Dict mapping layer name to number of pixels in given layer
        """
        grid_size = {}
        for layer in self.layer_colors:
            r, g, b, a = self.layer_colors[layer]
            grid_size[layer] = (
                (arr[:, :, 0] == r) & (arr[:, :, 1] == g) & (arr[:, :, 2] == b) & (arr[:, :, 3] == a)
            ).sum()
        return grid_size

    def _get_number_of_blank_pixels(self, arr):
        """
        This function counts the number of blank pixels
        Args:
            arr (np.ndarray): Numpy array with input RGBA data
        """
        r, g, b, a = self.background_rgba
        return ((arr[:, :, 0] == r) & (arr[:, :, 1] == g) & (arr[:, :, 2] == b) & (arr[:, :, 3] == a)).sum()
