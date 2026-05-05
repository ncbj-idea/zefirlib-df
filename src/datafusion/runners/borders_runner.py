import logging
from pathlib import Path

import click
from sqlalchemy.engine import Engine

from datafusion.configs.borders_config import BordersConfig
from datafusion.configs.config import Config
from datafusion.constants import CONFIG_PATH
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.readers.borders_reader import BordersReader
from datafusion.runners.runner import Runner
from datafusion.utils.setup_logging import setup_logging

setup_logging()

_logger = logging.getLogger(__name__)


class BordersRunner(Runner):
    def __init__(
        self,
        config: BordersConfig,
        engine: Engine,
        db_settings: DBSettings,
    ) -> None:
        super().__init__(config, engine)
        self.db_settings = db_settings

    def run(self) -> None:
        BordersReader(
            config=self.config,
            engine=self.engine,
            db_settings=self.db_settings,
        ).run()


def import_borders(config: Config) -> None:
    _logger.info("Importing borders with config")

    engine = get_engine()
    db_settings = DBSettings()
    BordersRunner(
        config=config.borders,
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
def import_borders_cli(config: Path) -> None:
    if not isinstance(config, Path):
        config = Path(config)
    cfg = Config.from_file(config)
    import_borders(cfg)


if __name__ == "__main__":
    _logger.info("Start import borders...")
    import_borders_cli()
