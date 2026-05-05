import logging
from pathlib import Path

import click

from datafusion.configs.config import Config
from datafusion.constants import CONFIG_PATH
from datafusion.database.session import get_engine
from datafusion.pvgis.data_merger import PVGISMerger
from datafusion.utils.setup_logging import setup_logging

setup_logging()

_logger = logging.getLogger(__name__)


def run_pvgis_merger(config_path: Path) -> None:
    _logger.info("Starting PVGIS Merger")

    config = Config.from_yml(config_path)

    engine = get_engine()
    pvgis_merger = PVGISMerger(
        config=config.pvgis,
        engine=engine,
    )

    pvgis_merger.get_data()
    pvgis_merger.save_data()


@click.command()
@click.option(
    "-c",
    "--config",
    default=Path(CONFIG_PATH),
    type=click.Path(exists=True, dir_okay=False),
)
def pvgis_merger_cli(config: Path) -> None:
    run_pvgis_merger(config)


if __name__ == "__main__":
    pvgis_merger_cli()
