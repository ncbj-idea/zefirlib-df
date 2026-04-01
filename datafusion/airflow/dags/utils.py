import json
from collections.abc import Callable
from pathlib import Path

from datafusion.configs.bdot_config import BDOTConfig
from datafusion.configs.borders_config import BordersConfig
from datafusion.configs.ceeb_config import CEEBConfig
from datafusion.configs.kiut_config import KIUTConfig

PossibleConfigs_T = BDOTConfig | CEEBConfig | KIUTConfig | BordersConfig


def create_config_from_path(config: Callable, config_path: Path) -> PossibleConfigs_T:
    if not config_path.exists():
        raise FileExistsError(f"File: {config_path} does not exists.")
    with open(config_path) as f:
        d = json.load(f)
    return config(**d)
