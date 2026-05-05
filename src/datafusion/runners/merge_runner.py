import logging
from pathlib import Path

import click
from sqlalchemy.engine import Engine

from datafusion.configs.config import Config
from datafusion.configs.merge_config import MergeConfig
from datafusion.constants import CONFIG_PATH
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.readers.merge_reader import MergeReader
from datafusion.runners.runner import Runner
from datafusion.utils.setup_logging import setup_logging

setup_logging()

_logger = logging.getLogger(__name__)


class MergeRunner(Runner):
    def __init__(
        self,
        config: MergeConfig,
        engine: Engine,
        db_settings: DBSettings,
    ) -> None:
        super().__init__(config, engine)
        self.db_settings = db_settings

    def run(self) -> None:
        _logger.info("Starting merge reader")
        MergeReader(
            config=self.config,
            engine=self.engine,
            db_settings=self.db_settings,
        ).run()


def merge_runner(config: Config) -> None:
    """Run the merge process with given configuration."""
    _logger.info("Starting merge runner")
    engine = get_engine()
    db_settings = DBSettings()

    runner = MergeRunner(
        config=config.merge_config,
        engine=engine,
        db_settings=db_settings,
    )
    runner.run()


@click.command()
@click.option(
    "-c",
    "--config",
    default=Path(CONFIG_PATH),
    type=click.Path(exists=True, dir_okay=False),
)
def merge_runner_cli(config: Path) -> None:
    """CLI interface for the merge runner."""
    if not isinstance(config, Path):
        config = Path(config)
    cfg = Config.from_file(config)
    merge_runner(cfg)


if __name__ == "__main__":
    merge_runner_cli()
