import logging
from pathlib import Path

import click
from sqlalchemy.engine import Engine

from datafusion.configs.ceeb_config import CEEBConfig
from datafusion.configs.config import Config
from datafusion.constants import CONFIG_PATH
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.readers.ceeb_reader import CEEBReader
from datafusion.runners.runner import Runner
from datafusion.utils.setup_logging import setup_logging

setup_logging()

_logger = logging.getLogger(__name__)


class CEEBRunner(Runner):
    def __init__(
        self,
        config: CEEBConfig,
        engine: Engine,
        db_settings: DBSettings,
    ):
        super().__init__(config, engine)
        self.db_settings = db_settings

    def run(self) -> None:
        CEEBReader(
            config=self.config,
            engine=self.engine,
            db_settings=self.db_settings,
        ).run()


def ceeb_runner(config: Config) -> None:
    _logger.info("Starting CEEB runner")
    engine = get_engine()

    db_settings = DBSettings()

    ceeb_reader = CEEBReader(
        config=config.ceeb,
        engine=engine,
        db_settings=db_settings,
    )
    ceeb_reader.run()


@click.command()
@click.option(
    "-c",
    "--config",
    default=Path(CONFIG_PATH),
    type=click.Path(exists=True, dir_okay=False),
)
def ceeb_runner_cli(config: Path) -> None:
    if not isinstance(config, Path):
        config = Path(config)
    cfg = Config.from_file(config)
    ceeb_runner(cfg)


if __name__ == "__main__":
    ceeb_runner_cli()
