import logging
from pathlib import Path

import click
from sqlalchemy.engine import Engine

from datafusion.configs.config import Config
from datafusion.constants import CONFIG_PATH
from datafusion.database.session import get_engine
from datafusion.runners.address_runner import address_runner
from datafusion.runners.bdot_runner import bdot_run
from datafusion.runners.borders_runner import import_borders
from datafusion.runners.ceeb_runner import ceeb_runner
from datafusion.runners.kiut_runner import run_kiut
from datafusion.runners.merge_runner import merge_runner
from datafusion.runners.postprocessing_runner import postprocessing_runner
from datafusion.utils.crud import get_process_state, save_process_state
from datafusion.utils.setup_logging import setup_logging

setup_logging()

_logger = logging.getLogger(__name__)

PROCESS_NAME = "all_steps"


def _run_data_fetch(config: Config, terc: str, engine: Engine) -> None:
    """Run steps 1-5 of the datafusion pipeline."""
    # Run BDOT
    _logger.info("Step 1/7: Running BDOT")
    bdot_run(config)

    # Run borders
    _logger.info("Step 2/7: Running borders")
    import_borders(config)

    # Run PRG (address runner)
    _logger.info("Step 3/7: Running PRG")
    address_runner(config)

    # Run KIUT
    _logger.info("Step 4/7: Running KIUT")
    run_kiut(config)

    save_process_state(PROCESS_NAME, terc, 5, "completed", engine)


def run_all(config: Config, force_from_start: bool = False, gui_mode: bool = False) -> bool:
    """Run all datafusion processes in sequence.

    Returns:
        True if pipeline completed fully, False if paused (gui_mode only).
    """
    _logger.info("Starting complete datafusion pipeline")

    terc = config.postprocessing.terc
    engine = get_engine()

    try:
        # Check if steps 1-5 need to run
        should_run_data_fetch = force_from_start
        if not force_from_start:
            state = get_process_state(PROCESS_NAME, terc, engine)
            if state and state.get("status") == "completed":
                _logger.info("Steps 1-5 already completed, skipping to step 6...")
            else:
                should_run_data_fetch = True

        if should_run_data_fetch:
            _run_data_fetch(config, terc, engine)
        # Run CEEB
        _logger.info("Step 5/7: Running CEEB")
        ceeb_runner(config)

        # Run merge
        _logger.info("Step 6/7: Running merge")
        merge_runner(config)

        # Run postprocessing
        _logger.info("Step 7/7: Running postprocessing")
        postprocessing_runner(config, gui_mode=gui_mode)

        if gui_mode:
            from datafusion.runners.postprocessing_runner import is_postprocessing_paused

            if is_postprocessing_paused(terc, engine):
                _logger.info("Postprocessing paused, waiting for user action")
                return False

        _logger.info("Complete datafusion pipeline finished successfully")
        return True

    except Exception as e:
        _logger.error("Error in datafusion pipeline: %s", str(e))
        raise


@click.command()
@click.option(
    "-c",
    "--config",
    default=Path(CONFIG_PATH),
    type=click.Path(exists=True, dir_okay=False),
    help="Path to configuration file",
)
@click.option(
    "--force-from-start",
    is_flag=True,
    default=False,
    help="Start from beginning instead of resuming from paused state",
)
def run_all_cli(config: Path, force_from_start: bool) -> None:
    """Run all datafusion processes in sequence: bdot, borders, kiut, ceeb, prg, report, merge."""
    if not isinstance(config, Path):
        config = Path(config)
    cfg = Config.from_file(config)
    run_all(cfg, force_from_start=force_from_start)


if __name__ == "__main__":
    run_all_cli()
