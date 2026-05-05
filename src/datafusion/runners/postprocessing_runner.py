from __future__ import annotations

import logging
from pathlib import Path

import click
from sqlalchemy.engine import Engine

from datafusion.configs.config import Config
from datafusion.configs.postprocessing_config import PostprocessingConfig
from datafusion.constants import CONFIG_PATH
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.postprocessing.assign_termo_class import run_assign_termo_class
from datafusion.postprocessing.creating_operat_losowania import run_creating_operat_losowania
from datafusion.postprocessing.estimation_a import run_estimation_a
from datafusion.postprocessing.estimation_b import run_estimation_b
from datafusion.postprocessing.find_global_values import run_find_global_values
from datafusion.postprocessing.protostrefy import run_protostrefy
from datafusion.postprocessing.sampling_miasta import run_sampling_miasta
from datafusion.runners.runner import Runner
from datafusion.utils.crud import get_process_state, save_process_state
from datafusion.utils.setup_logging import setup_logging

setup_logging()
_logger = logging.getLogger(__name__)


def get_base_directories(terc: str, config: PostprocessingConfig) -> dict[str, Path]:
    """
    Returns: Path to the base city directory, where all postprocessing files are stored.
    """
    output_base_dir = config.output_path / terc / "postprocessing"
    input_base_dir = config.input_path / terc / "postprocessing"
    input_base_dir.mkdir(parents=True, exist_ok=True)
    output_base_dir.mkdir(parents=True, exist_ok=True)

    return {
        "input": input_base_dir,
        "output": output_base_dir,
    }


class Postprocessing(Runner):
    """Runner of postprocessing"""

    PROCESS_NAME = "postprocessing"

    def __init__(
        self, config: PostprocessingConfig, engine: Engine, db_settings: DBSettings, gui_mode: bool = False
    ) -> None:
        super().__init__(config=config, engine=engine)
        self.db_settings = db_settings
        self.gui_mode = gui_mode

    def _load_state(self) -> dict | None:
        """Load postprocessing state from database."""
        return get_process_state(self.PROCESS_NAME, self.config.terc, self.engine)

    def _save_state(self, step: int, status: str) -> None:
        """Save postprocessing state to database."""
        save_process_state(
            process_name=self.PROCESS_NAME,
            terc=self.config.terc,
            step=step,
            status=status,
            engine=self.engine,
        )

    def run(self) -> None:
        _logger.info("Postprocessing started")

        state = self._load_state()
        is_resumed = state and state.get("status") == "paused"

        if is_resumed:
            _logger.info("Resuming from paused state (step 4)")

        io_dirs = get_base_directories(self.config.terc, self.config)
        input_dir, output_dir = io_dirs["input"], io_dirs["output"]

        if not is_resumed:
            _logger.info("Step 1/6: creating_operat_losowania...")
            run_creating_operat_losowania(self.engine, self.config)

            _logger.info("Step 2/6: find_global_values...")
            global_values = run_find_global_values(self.engine, self.config, output_dir)

            _logger.info("Step 3/6: sampling_miasta...")
            run_sampling_miasta(output_dir, self.engine, self.config)

            self._save_state(3, "paused")
            if self.gui_mode:
                _logger.info("Paused: place data files in %s/inventory_files/", input_dir)
                return
            print("\n")
            print("=" * 60)
            print("ACTION REQUIRED: Please place data files in folder:")
            print(f"  {input_dir}/inventory_files/")
            print("After placing the files, press Enter to continue...")
            print("OR type 'exit' or just 'q' to close and resume later...")
            print("=" * 60)
            user_input = input("Press Enter to continue after placing data files in input folder...")
            if user_input.strip().lower() == "exit" or user_input.strip().lower() == "q":
                _logger.info("Exiting. Run again to resume from this point.")
                return
        else:
            global_values = run_find_global_values(self.engine, self.config, output_dir)

        _logger.info("Step 4/6: assign_termo_class...")
        run_assign_termo_class(input_dir, self.engine, self.config)

        _logger.info("Step 5A/6: estimation_A...")
        run_estimation_a(self.engine, self.config, global_values)

        _logger.info("Step 5B/6: estimation_B...")
        run_estimation_b(self.engine, self.config, global_values)

        _logger.info("Step 6/6: protostrefy...")
        run_protostrefy(output_dir, self.engine, self.config)

        self._save_state(6, "completed")
        _logger.info("\n 🏁 Postprocessing successfully finished 🏁")


def is_postprocessing_paused(terc: str, engine: Engine) -> bool:
    """Check whether postprocessing is in a paused state for the given TERC."""
    state = get_process_state(Postprocessing.PROCESS_NAME, terc, engine)
    return state is not None and state.get("status") == "paused"


def postprocessing_runner(config: Config, gui_mode: bool = False) -> None:
    """Run the postprocessing pipeline with the given configuration."""
    _logger.info("Starting postprocessing runner")
    engine = get_engine()
    db_settings = DBSettings()

    runner = Postprocessing(
        config=config.postprocessing,
        engine=engine,
        db_settings=db_settings,
        gui_mode=gui_mode,
    )
    runner.run()


@click.command()
@click.option(
    "-c",
    "--config",
    default=Path(CONFIG_PATH),
    type=click.Path(exists=True, dir_okay=False),
    help="Path to config.yml",
)
def postprocessing_runner_cli(config: Path) -> None:
    """CLI interface for the postprocessing runner."""
    if not isinstance(config, Path):
        config = Path(config)
    cfg = Config.from_file(config)
    postprocessing_runner(cfg)


if __name__ == "__main__":
    postprocessing_runner_cli()
