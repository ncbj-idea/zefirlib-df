import logging
from pathlib import Path

import click

from datafusion.configs.config import Config
from datafusion.constants import CONFIG_PATH
from datafusion.database.initialize import initialize_kiut_util_database
from datafusion.database.session import get_engine
from datafusion.readers.kiut_reader import KIUTReader
from datafusion.runners.runner import Runner
from datafusion.utils.setup_logging import setup_logging

setup_logging()

_logger = logging.getLogger(__name__)


class KIUTRunner(Runner):
    def run(self) -> None:
        KIUTReader(
            config=self.config,
            engine=self.engine,
        ).run()


def run_kiut(config: Config) -> None:
    _logger.info("Running KIUT with config")
    engine = get_engine()
    initialize_kiut_util_database(db_engine=engine, kiut_config=config.kiut)
    KIUTRunner(
        config=config.kiut,
        engine=engine,
    ).run()


@click.command()
@click.option(
    "-c",
    "--config",
    default=Path(CONFIG_PATH),
    type=click.Path(exists=True, dir_okay=False),
)
def kiut_runner_cli(config: Path) -> None:
    if not isinstance(config, Path):
        config = Path(config)
    cfg = Config.from_file(config)
    run_kiut(cfg)


if __name__ == "__main__":
    kiut_runner_cli()
