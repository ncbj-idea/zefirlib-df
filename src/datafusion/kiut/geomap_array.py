import numpy as np
from PIL import Image
from shapely import Polygon
from shapely.geometry import box


class GeomapRGBAArray:
    """
    Class for representing a geomap with RGBA data.
    """

    def __init__(self, array: np.ndarray, min_x: float, min_y: float, max_x: float, max_y: float) -> None:
        """
        Constructor of GeomapRGBAArray class.

        Args:
            array (np.ndarray): Array with RGBA data.
            min_x (float): Minimum x value.
            min_y (float): Minimum y value.
            max_x (float): Maximum x value.
            max_y (float): Maximum y value.
        """
        self._array = array
        self.min_x = min_x
        self.min_y = min_y
        self.max_x = max_x
        self.max_y = max_y

    @property
    def array(self) -> np.ndarray:
        """
        Returns array with RGBA data.

        """
        return self._array

    @array.setter
    def array(self, arr: np.ndarray) -> None:
        """
        Set array with RGBA data.
        Args:
            arr (np.ndarray): Array with RGBA data.


        """
        if not isinstance(arr, np.ndarray):
            raise TypeError("self.array should be an arrayb type")
        if len(arr.shape) == 3:
            msg = "self.array should be 3 dimension array"
            raise ValueError(msg)
        if arr.shape[2] == 4:
            msg = "self.array should be 3 dimension array that represents R,G,B and alpha channel"
            raise ValueError(msg)
        self._array = arr

    @property
    def scale_x(self) -> float:
        """
        Returns scale x value.
        Returns: scaled x value.

        """
        return (self.max_x - self.min_x) / self.array.shape[1]

    @property
    def scale_y(self) -> float:
        """
        Returns scale y value.
        Returns: scaled y value.

        """
        return (self.max_y - self.min_y) / self.array.shape[0]

    def get_geom(self) -> Polygon:
        """
        Returns a polygon geometry of the array.
        Returns (Polygon): Polygon geometry of the array.

        """
        return box(minx=self.min_x, miny=self.min_y, maxx=self.max_x, maxy=self.max_y)

    def x(self, col_idx: int) -> float:
        """
        Returns x value for a given column index
        Args:
            col_idx (int): Column index

        Returns:
            Returns x coordinates of the column.
        """
        return self.min_x + col_idx * self.scale_x

    def y(self, row_idx: int) -> float:
        """
        Return y value for a given row index
        Args:
            row_idx (int): Row index

        Returns:
            Returns y coordinates of the row.
        """
        return self.max_y - row_idx * self.scale_y

    def get_image(self) -> Image:
        """
        Return a PIL image of the array.
        Returns:
            Returns PIL image of the array.
        """
        return Image.fromarray(self.array)
