import logging
from pathlib import Path

import click

from datafusion.configs.config import Config
from datafusion.constants import CONFIG_PATH
from datafusion.database.session import get_engine
from datafusion.reporting.reporting import Reporting

_logger = logging.getLogger(__name__)


def run_report(config: Config) -> None:
    Reporting(
        config=config.global_config,
        db_engine=get_engine(),
    ).run()


@click.command()
@click.option(
    "-c",
    "--config",
    default=Path(CONFIG_PATH),
    type=click.Path(exists=True, dir_okay=False),
)
def run_report_cli(config: Path) -> None:
    config = Config.from_yml(Path(config))
    run_report(config)


if __name__ == "__main__":
    _logger.info("Start report runner...")
    run_report_cli()
