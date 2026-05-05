import logging
from pathlib import Path

import click
from sqlalchemy.engine import Engine

from datafusion.configs.config import Config
from datafusion.configs.pvgis_config import PVGISConfig
from datafusion.constants import CONFIG_PATH
from datafusion.database.session import get_engine
from datafusion.readers.pvgis_reader import PVGISReader
from datafusion.runners.runner import Runner
from datafusion.utils.setup_logging import setup_logging

setup_logging()

_logger = logging.getLogger(__name__)


class PVGISRunner(Runner):
    def __init__(
        self,
        config: PVGISConfig,
        engine: Engine,
    ) -> None:
        super().__init__(config=config, engine=engine)

    def run(self) -> None:
        PVGISReader(
            config=self.config,
            engine=self.engine,
        ).run()


def run_pvgis(config_path: Path) -> None:
    _logger.info("Starting PVGIS runner")

    config = Config.from_yml(Path(config_path)).pvgis

    _logger.info(f"Running PVGIS with parameters: {config.short_rep()}")
    engine = get_engine()
    PVGISRunner(config=config, engine=engine).run()


@click.command()
@click.option(
    "-c",
    "--config",
    default=Path(CONFIG_PATH),
    type=click.Path(exists=True, dir_okay=False),
)
def pvgis_runner_cli(config: Path) -> None:
    run_pvgis(config)


if __name__ == "__main__":
    pvgis_runner_cli()
