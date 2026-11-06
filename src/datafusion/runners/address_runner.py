import logging
from pathlib import Path

import click
from sqlalchemy.engine import Engine

from datafusion.configs.address_config import AddressConfig
from datafusion.configs.borders_config import BordersConfig
from datafusion.configs.config import Config
from datafusion.constants import CONFIG_PATH
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.readers.address_reader import AddressReader
from datafusion.runners.runner import Runner
from datafusion.utils.setup_logging import setup_logging

setup_logging()


_logger = logging.getLogger(__name__)


class AddressRunner(Runner):
    def __init__(
        self,
        config: AddressConfig,
        engine: Engine,
        db_settings: DBSettings,
        borders_config: BordersConfig | None = None,
    ) -> None:
        super().__init__(config=config, engine=engine)
        self.db_settings = db_settings
        self.borders_config = borders_config

    def run(self) -> None:
        AddressReader(
            config=self.config,
            db_engine=self.engine,
            db_settings=self.db_settings,
            borders_config=self.borders_config,
        ).run()


def address_runner(config: Config):
    _logger.info("Running address runner")

    engine = get_engine()
    db_settings = DBSettings()
    AddressRunner(
        config=config.address,
        engine=engine,
        db_settings=db_settings,
        borders_config=config.borders,
    ).run()


@click.command()
@click.option(
    "-c",
    "--config",
    default=Path(CONFIG_PATH),
    type=click.Path(exists=True, dir_okay=False),
)
def address_runner_cli(config: Path) -> None:
    if not isinstance(config, Path):
        config = Path(config)
    cfg = Config.from_file(config)
    address_runner(cfg)


if __name__ == "__main__":
    address_runner_cli()
