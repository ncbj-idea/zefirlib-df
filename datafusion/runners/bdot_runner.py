import logging
from pathlib import Path

import click
from sqlalchemy.engine import Engine

from datafusion.configs.bdot_config import BDOTConfig
from datafusion.configs.config import Config
from datafusion.constants import CONFIG_PATH
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.readers.bdot_reader import BDOTReader
from datafusion.runners.runner import Runner
from datafusion.utils.setup_logging import setup_logging

setup_logging()

_logger = logging.getLogger(__name__)


class BDOTRunner(Runner):
    def __init__(
        self,
        config: BDOTConfig,
        engine: Engine,
        db_settings: DBSettings,
    ) -> None:
        super().__init__(config, engine)
        self.db_settings = db_settings

    def run(self) -> None:
        BDOTReader(
            config=self.config,
            engine=self.engine,
            db_settings=self.db_settings,
        ).run()


def bdot_run(config: Config) -> None:
    _logger.info("Running BDOT runner")
    engine = get_engine()
    db_settings = DBSettings()

    BDOTRunner(
        config=config.bdot,
        engine=engine,
        db_settings=db_settings,
    ).run()


@click.command()
@click.option(
    "-c",
    "--config",
    default=Path(CONFIG_PATH),
    type=click.Path(exists=True, dir_okay=False),
)
def bdot_runner_cli(config: Path) -> None:
    if not isinstance(config, Path):
        config = Path(config)
    cfg = Config.from_file(config)
    bdot_run(cfg)


if __name__ == "__main__":
    bdot_runner_cli()
