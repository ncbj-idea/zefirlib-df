from abc import ABC, abstractmethod
from typing import TypeVar

import numpy as np

from datafusion.kiut.layers import LayerNames

ExistingLayers = list[LayerNames]


class LayerChecker(ABC):
    """
    This is an abstract base class that defines the interface for all layer checkers.
    """

    @abstractmethod
    def get_existing_layers(self, array: np.ndarray) -> ExistingLayers:
        pass


LayerChecker_T = TypeVar("LayerChecker_T", bound=LayerChecker)
