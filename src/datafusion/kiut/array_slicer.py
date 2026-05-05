import logging
from itertools import product
from typing import Any

import numpy as np

from datafusion.kiut.geomap_array import GeomapRGBAArray
from datafusion.kiut.layers import LayerNames

logger = logging.getLogger(__name__)


ExistingLayers = list[LayerNames]


class ArraySlicer:
    """
    ArraySlicer slice bigger arrays of geo data to smaller pieces.

    The aim of this class is to allow you to slice the biggest arrays.
    """

    def __init__(self, number_of_slices_of_image_side: int = 100) -> None:
        """

        Args:
            number_of_slices_of_image_side (int, optional): This will slice the array into n pieces Defaults to 100.
        """
        self.number_of_slices_of_image_side = number_of_slices_of_image_side

    def to_tiles(
        self,
        obj: GeomapRGBAArray,
    ) -> list[tuple[GeomapRGBAArray, dict[str, Any]]]:
        """
        This functino performs slicing the geodata Array to smaller pieces, preserving the RGBA data.
        Args:
            obj (GeomapRGBAArray): GeomapRGBAArray object instance

        Returns:

        """
        x_idx = np.linspace(0, obj.array.shape[1], self.number_of_slices_of_image_side + 1, dtype="int")
        y_idx = np.linspace(0, obj.array.shape[0], self.number_of_slices_of_image_side + 1, dtype="int")
        x_slices = zip(x_idx[:-1], x_idx[1:])
        y_slices = zip(y_idx[:-1], y_idx[1:])
        slices = list(product(y_slices, x_slices))
        list_of_objs = []
        for row_slice, col_slice in slices:
            geoarr = GeomapRGBAArray(
                array=obj.array[slice(*row_slice), slice(*col_slice)],
                min_x=obj.x(col_idx=col_slice[0]),
                min_y=obj.y(row_idx=row_slice[0]),
                max_x=obj.x(col_idx=col_slice[1]),
                max_y=obj.y(row_idx=row_slice[1]),
            )
            debug_data = {"row_slice": str(row_slice), "col_slice": str(col_slice)}
            el = (geoarr, debug_data)
            list_of_objs.append(el)
        return list_of_objs
