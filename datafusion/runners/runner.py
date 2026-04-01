from abc import ABC, abstractmethod

from sqlalchemy.engine import Engine

from datafusion.configs.bdot_config import BDOTConfig
from datafusion.configs.borders_config import BordersConfig
from datafusion.configs.ceeb_config import CEEBConfig
from datafusion.configs.kiut_config import KIUTConfig
from datafusion.configs.merge_config import MergeConfig
from datafusion.configs.pvgis_config import PVGISConfig

CONFIG = BDOTConfig | CEEBConfig | KIUTConfig | BordersConfig | PVGISConfig | MergeConfig


class Runner(ABC):
    def __init__(
        self,
        config: CONFIG,
        engine: Engine,
    ) -> None:
        self.config = config
        self.engine = engine

    @abstractmethod
    def run(self) -> None:
        pass
