import logging
import os
import sys
from pathlib import Path
from typing import Final

import yaml
from PySide6.QtCore import QObject, QProcess, Qt, QThread, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from datafusion.configs.config import Config
from datafusion.runners.all_runner import run_all
from datafusion.utils.setup_logging import setup_logging

os.environ["LOG_CFG"] = "logging_gui.yml"
setup_logging()
_logger = logging.getLogger(__name__)


def _resolve_configs_dir() -> Path:
    """Resolve configs directory for local and Docker runs.

    Priority:
    1) DATAFUSION_CONFIG_DIR env var
    2) /datafusion/configs (bind-mounted workspace in Docker)
    3) ./configs (local/dev default)
    """
    env_dir = os.getenv("DATAFUSION_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)

    docker_dir = Path("/datafusion/configs")
    if docker_dir.exists():
        return docker_dir

    return Path("configs")


CONFIGS_DIR: Final[Path] = _resolve_configs_dir()
CONFIG_FILE: Final[Path] = CONFIGS_DIR / "config.yml"
GLOBAL_CONFIG: Final[Path] = CONFIGS_DIR / "global.yml"
CEEB_CONFIG: Final[Path] = CONFIGS_DIR / "data_sources" / "ceeb.yml"
REPORT_CONFIG: Final[Path] = CONFIGS_DIR / "data_sources" / "report.yml"


def _read_yaml(path: Path) -> dict:
    """Read a single YAML file and return its contents as a dict."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path: Path, data: dict) -> None:
    """Write a dict to a YAML file, preserving existing keys not in data."""
    existing = _read_yaml(path)
    existing.update(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(existing, f, allow_unicode=True, sort_keys=False)


def _load_gui_config() -> dict:
    """Load GUI-relevant config from individual YAML files in configs/ directory.

    Reads global.yml, data_sources/ceeb.yml, and data_sources/report.yml.
    Returns a dict with 'global', 'ceeb', and 'report' sections.
    """
    return {
        "global": _read_yaml(GLOBAL_CONFIG),
        "ceeb": _read_yaml(CEEB_CONFIG),
        "report": _read_yaml(REPORT_CONFIG),
    }


def _save_gui_config(config_dict: dict) -> None:
    """Save GUI-relevant config back to individual YAML files in configs/ directory."""
    if "global" in config_dict:
        _write_yaml(GLOBAL_CONFIG, config_dict["global"])
    if "ceeb" in config_dict:
        _write_yaml(CEEB_CONFIG, config_dict["ceeb"])
    if "report" in config_dict:
        _write_yaml(REPORT_CONFIG, config_dict["report"])


class PipelineWorker(QThread):
    """Worker thread for running the pipeline to avoid blocking GUI."""

    log_signal = Signal(str)
    finished_signal = Signal(bool, str)  # success, message

    def __init__(self, config_dict: dict):
        super().__init__()
        self.config_dict = dict(config_dict)

    def _create_config(self) -> Config:
        """Create Config object from config_dict without writing to disk."""
        return Config.from_dict(self.config_dict, validate_files=False)

    def update_config_inputs(
        self,
        terc_code: str | None = None,
        ceeb_devices_path: str | None = None,
        ceeb_class_path: str | None = None,
    ):
        if terc_code:
            self.config_dict.setdefault("global", {})["terc"] = terc_code
        if ceeb_devices_path:
            self.config_dict.setdefault("ceeb", {})["ceeb_devices_file_path"] = ceeb_devices_path
        if ceeb_class_path:
            self.config_dict.setdefault("ceeb", {})["ceeb_class_file_path"] = ceeb_class_path

    def run(self):
        """Run the pipeline in a separate thread."""
        try:
            terc_for_log = (self.config_dict.get("global", {}) or {}).get("terc")
            _logger.info(f"Starting datafusion pipeline with TERC code: {terc_for_log}")
            self.log_signal.emit("Processing started...")

            config = self._create_config()
            self.log_signal.emit("Config created in-memory")

            run_all(config)

            message = f"Pipeline completed successfully for TERC: {terc_for_log}"
            self.log_signal.emit(message)
            self.finished_signal.emit(True, message)

        except Exception as e:
            error_msg = f"Error running pipeline: {str(e)}"
            _logger.error(error_msg)
            _logger.exception(e)
            self.log_signal.emit(error_msg)
            self.finished_signal.emit(False, error_msg)


class Runner(QObject):
    """Generic process runner that executes a Python module or script and streams logs."""

    started = Signal(str)  # emitted with the command line
    output = Signal(str)  # stdout lines
    error = Signal(str)  # stderr lines
    finished = Signal(int, int)  # exitCode, exitStatus

    def __init__(self, script: str, args: list[str] | None = None, use_module: bool = True, cwd: Path | None = None):
        super().__init__()
        self.script = script
        self.args = args or []
        self.use_module = use_module
        self.cwd = str(cwd) if cwd else None
        self._proc = QProcess()

        # Connect QProcess signals
        self._proc.readyReadStandardOutput.connect(self._on_stdout)
        self._proc.readyReadStandardError.connect(self._on_stderr)
        # Forward finished via a slot to our custom signal
        self._proc.finished.connect(self._on_finished_proc)

    def start(self):
        if self.use_module:
            program = sys.executable
            arguments = ["-m", self.script, *self.args]
        else:
            program = self.script
            arguments = self.args

        cmd_str = " ".join([program] + arguments)
        self.started.emit(cmd_str)
        if self.cwd:
            self._proc.setWorkingDirectory(self.cwd)
        # Merge channels? Keep separate to style differently if desired
        self._proc.setProcessChannelMode(QProcess.SeparateChannels)
        self._proc.start(program, arguments)

    def terminate(self):
        try:
            self._proc.kill()
        except Exception:
            pass

    def _on_stdout(self):
        data = bytes(self._proc.readAllStandardOutput()).decode(errors="ignore")
        if data:
            self.output.emit(data)

    def _on_stderr(self):
        data = bytes(self._proc.readAllStandardError()).decode(errors="ignore")
        if data:
            self.error.emit(data)

    def _on_finished_proc(self, exit_code, exit_status):
        # Emit custom finished signal with normalized values
        try:
            status_int = int(exit_status)
        except Exception:
            status_int = 0
        self.finished.emit(int(exit_code), status_int)


class DataFusionGUI(QMainWindow):
    """Main GUI window for DataFusion Pipeline."""

    def __init__(self, config_dict: dict):
        super().__init__()
        self.worker = None
        self.config_dict = dict(config_dict)
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("DataFusion")
        self.setGeometry(100, 100, 650, 800)
        self.center_on_screen()

        def add_section_header(text: str) -> None:
            container = QWidget()
            h = QHBoxLayout(container)
            h.setContentsMargins(0, 12, 0, 8)
            h.setSpacing(12)
            label = QLabel(text)
            label.setFont(QFont("Arial", 14, QFont.Bold))
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            line.setStyleSheet("background-color: #dee2e6;")
            line.setFixedHeight(1)
            h.addWidget(label)
            h.addWidget(line, 1)
            layout.addWidget(container)

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Title
        title_label = QLabel("DataFusion")
        title_label.setFont(QFont("Arial", 20, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        layout.addSpacing(12)

        add_section_header("Informacje ogólne")

        link_label = QLabel(
            'Wyszukaj w rejestrze <a href="https://eteryt.stat.gov.pl/eTeryt/rejestr_teryt/udostepnianie_danych/baza_teryt/uzytkownicy_indywidualni/wyszukiwanie/wyszukiwanie.aspx?contrast=default">eteryt.stat.gov.pl</a>'
        )
        link_label.setOpenExternalLinks(True)
        link_label.setAlignment(Qt.AlignRight)
        link_label.setFont(QFont("Arial", 12))
        layout.addWidget(link_label)

        # TERC Code input section
        input_layout = QHBoxLayout()
        terc_label = QLabel("Kod TERC")
        terc_label.setFixedWidth(200)
        self.terc_input = QLineEdit()
        self.terc_input.setPlaceholderText("Podaj 7-cyfrowy identyfikator")

        terc_initial = (self.config_dict.get("global") or {}).get("terc")
        if terc_initial:
            self.terc_input.setText(str(terc_initial))

        input_layout.addWidget(terc_label)
        input_layout.addWidget(self.terc_input)
        layout.addLayout(input_layout)

        add_section_header("Ścieżki do plików CEEB")

        ceeb_devices_initial = (self.config_dict.get("ceeb") or {}).get("ceeb_devices_file_path")
        self.ceeb_devices_path_input, self.ceeb_devices_pick_button = self._add_path_row(
            layout,
            "Urządzenia",
            "Wybierz plik .csv/.xlsx/.xls…",
            initial_value=ceeb_devices_initial,
            pick_fn=self.pick_file,
        )

        ceeb_class_file_path = (self.config_dict.get("ceeb") or {}).get("ceeb_class_file_path")
        self.ceeb_classes_path_input, self.ceeb_classes_pick_button = self._add_path_row(
            layout,
            "Klasy",
            "Wybierz plik .csv/.xlsx/.xls…",
            initial_value=ceeb_class_file_path,
            pick_fn=self.pick_file,
        )

        layout.addSpacing(6)

        # Save report checkbox
        self.save_report_checkbox = QCheckBox("Zapisz dane do pliku buildings_report.xls")
        self.save_report_checkbox.setObjectName("saveReportCheckbox")
        layout.addWidget(self.save_report_checkbox)

        add_section_header("Agregacja odbiorców")

        self.inventory_path_input, self.inventory_pick_button = self._add_path_row(
            layout,
            "Folder z inwentaryzacją",
            "Wybierz folder",
            pick_fn=self.pick_directory,
        )

        # --- Validation errors ---
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: blue;")
        self.status_label.setFixedHeight(24)
        layout.addWidget(self.status_label)

        # --- Terminal output ---
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("terminal")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(300)
        self.log_view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        layout.addWidget(self.log_view)

        # --- Buttons at the bottom ---
        button_layout = QHBoxLayout()

        self.run_button = QPushButton("Pobierz dane")
        self.run_button.setFixedWidth(140)
        self.run_button.clicked.connect(self.run_pipeline)
        self.run_button.setObjectName("primaryButton")

        self.postprocessing_button = QPushButton("Agreguj odbiorców")
        self.postprocessing_button.setFixedWidth(180)
        self.postprocessing_button.setObjectName("primaryButton")
        self.postprocessing_button.clicked.connect(self.run_postprocessing)

        self.exit_button = QPushButton("Zamknij")
        self.exit_button.setFixedWidth(90)
        self.exit_button.clicked.connect(self.close)
        self.exit_button.setObjectName("secondaryContainedButton")

        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.postprocessing_button)
        button_layout.addWidget(self.exit_button)
        button_layout.setContentsMargins(0, 12, 0, 12)
        layout.addLayout(button_layout)

        self.terc_input.setFocus()
        self._apply_stylesheet()

    def run_pipeline(self):
        """Run the pipeline with the entered TERC code."""
        terc_code = self.terc_input.text().strip()

        if not terc_code:
            self._show_error("Podaj kod TERC")
            return

        # CEEB paths
        ceeb_devices_path = self._validate_file_path(
            self.ceeb_devices_path_input.text(),
            "CEEB Urządzenia",
        )
        if ceeb_devices_path is None:
            return

        ceeb_classes_path = self._validate_file_path(
            self.ceeb_classes_path_input.text(),
            "CEEB Klasy",
        )
        if ceeb_classes_path is None:
            return

        # Clear previous output and update status
        self.log_view.clear()
        self._show_status("Uruchomiono proces...")

        # Disable buttons during execution
        self.run_button.setEnabled(False)
        self.postprocessing_button.setEnabled(False)

        # Update in-memory config
        self.config_dict.setdefault("global", {})["terc"] = terc_code
        if ceeb_devices_path:
            self.config_dict.setdefault("ceeb", {})["ceeb_devices_file_path"] = ceeb_devices_path
        if ceeb_classes_path:
            self.config_dict.setdefault("ceeb", {})["ceeb_class_file_path"] = ceeb_classes_path

        # Run pipeline using PipelineWorker (in-process, not subprocess)
        self.worker = PipelineWorker(self.config_dict)
        self.worker.log_signal.connect(self._append_log)
        self.worker.finished_signal.connect(self._on_pipeline_finished)
        self.worker.start()

    def _append_log(self, message: str):
        """Append message to terminal log view."""
        self.log_view.appendPlainText(message)
        self.log_view.ensureCursorVisible()

    def _on_pipeline_finished(self, success: bool, message: str):
        """Handle pipeline completion."""
        self.run_button.setEnabled(True)
        self.postprocessing_button.setEnabled(True)
        if success:
            self._show_status("Proces zakończony sukcesem")
        else:
            self._show_error(f"Proces zakończony błędem: {message}")

    def _apply_stylesheet(self) -> None:
        """Load QSS from file, resolve CSS variable references, and apply.
        Tries multiple paths:
        1. Site-packages location (installed package)
        2. Workspace location (mounted /datafusion)
        3. Relative to __file__ (development)
        """
        try:
            # Try multiple possible locations for the stylesheet
            possible_paths = [
                Path(__file__).resolve().parents[1] / "gui" / "style.qss",
                Path("/datafusion/datafusion/gui/style.qss"),
                Path("/app/datafusion/gui/style.qss"),
            ]

            style_path = None
            for path in possible_paths:
                if path.exists():
                    style_path = path
                    break

            if not style_path:
                _logger.debug(f"Stylesheet not found in any of: {possible_paths}")
                return

            content = style_path.read_text(encoding="utf-8")

            # Extract CSS variables defined under :root { --var: value; }
            import re

            var_pattern = re.compile(r"--([a-zA-Z0-9_-]+)\s*:\s*([^;]+);")
            variables = {m.group(1): m.group(2).strip() for m in var_pattern.finditer(content)}

            # Replace var(--name) occurrences with the variable values
            def repl_var(match):
                name = match.group(1)
                return variables.get(name, match.group(0))

            content_resolved = re.sub(r"var\(--([a-zA-Z0-9_-]+)\)", repl_var, content)
            # Remove the :root block (Qt QSS doesn't use it)
            content_resolved = re.sub(r":root\s*\{.*?\}", "", content_resolved, flags=re.DOTALL)
            self.setStyleSheet(content_resolved)
        except Exception as e:
            _logger.warning(f"Failed to apply stylesheet: {e}")

    def center_on_screen(self) -> None:
        """Move the window to the center of the primary screen."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        x = geom.center().x() - self.width() // 2
        y = geom.center().y() - self.height() // 2
        self.move(x, y)

    def close_event(self, event):
        """Handle window close event."""
        try:
            if getattr(self, "current_runner", None):
                self.current_runner.terminate()
        except Exception:
            pass
        event.accept()

    def _show_error(self, message: str) -> None:
        """Display an error message in the status label."""
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: red;")

    def _show_status(self, message: str) -> None:
        """Display a success/info message in the status label."""
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: green;")

    def _add_path_row(
        self,
        layout: QVBoxLayout,
        label_text: str,
        placeholder: str,
        initial_value: str | None = None,
        pick_fn: callable = None,
    ) -> tuple[QLineEdit, QPushButton]:
        """Create a label + line edit + pick button row and add it to the layout."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        label = QLabel(label_text)
        label.setFixedWidth(200)
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        if initial_value:
            line_edit.setText(str(initial_value))
        btn = QPushButton("Wybierz")
        btn.setObjectName("primaryOutlinedButton")
        btn.setFixedHeight(28)
        if pick_fn:
            btn.clicked.connect(lambda: pick_fn(line_edit))
        row.addWidget(label)
        row.addWidget(line_edit)
        row.addWidget(btn)
        layout.addLayout(row)
        return line_edit, btn

    _ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

    def _validate_file_path(self, raw_path: str, field_name: str) -> str | None:
        """Validate a file path input. Returns cleaned path or None on error."""
        path_str = raw_path.strip()
        if not path_str:
            self._show_error(f"Podaj ścieżkę do pliku {field_name}")
            return None
        p = Path(path_str)
        if not p.is_file() or p.suffix.lower() not in self._ALLOWED_EXTENSIONS:
            self._show_error(
                f"Nieprawidłowa ścieżka do pliku {field_name}. Plik nie istnieje lub ma nieobsługiwany format"
            )
            return None
        return path_str

    def _start_runner(self, module: str, args: list[str]) -> None:
        """Create a Runner, wire its signals, and start it."""
        self.current_runner = Runner(script=module, args=args, use_module=True, cwd=Path.cwd())
        self.current_runner.started.connect(lambda cmd: self._append_log(f"Start: {cmd}\n"))
        self.current_runner.output.connect(self._append_log)
        self.current_runner.error.connect(lambda e: self._append_log(f"[STDERR] {e}"))
        self.current_runner.finished.connect(self._on_finished)
        self.current_runner.start()

    def pick_file(self, target_input: QLineEdit):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik CSV/Excel",
            str(Path.cwd()),
            "Pliki CSV/Excel (*.csv *.xlsx *.xls);;Wszystkie pliki (*)",
        )
        if filename:
            target_input.setText(filename)

    def pick_directory(self, target_input: QLineEdit):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Wybierz folder",
            str(Path.cwd()),
        )
        if directory:
            target_input.setText(directory)

    def _check_terc_in_db(self, terc_code: str) -> bool:
        """Check whether data for the given TERC code exists in the database."""
        try:
            from sqlalchemy.orm import Session

            from datafusion.database.models.mapping_import_to_terc import MappingImportToTerc
            from datafusion.database.session import get_engine

            engine = get_engine()
            with Session(engine) as session:
                row = session.query(MappingImportToTerc).filter_by(terc=terc_code).first()
                return row is not None
        except Exception as exc:
            _logger.warning("Nie udało się sprawdzić TERC w bazie danych: %s", exc)
            return False

    def run_postprocessing(self):
        """Run the postprocessing pipeline."""
        terc_code = self.terc_input.text().strip()
        if not terc_code:
            self._show_error("Podaj kod TERC")
            return

        inventory_path = self.inventory_path_input.text().strip()
        if not inventory_path:
            self._show_error("Podaj ścieżkę do folderu inwentaryzacji")
            return

        if not Path(inventory_path).is_dir():
            self._show_error("Folder inwentaryzacji nie istnieje")
            return

        # Clear previous output and update status
        self.log_view.clear()
        self._show_status("Uruchomiono agregację...")

        # Disable buttons during execution
        self.postprocessing_button.setEnabled(False)
        self.run_button.setEnabled(False)

        self._start_runner("datafusion.runners.postprocessing_runner", ["--config", str(CONFIG_FILE)])


def gui_runner_cli() -> None:
    """CLI entry point for the GUI runner."""
    app = QApplication([])
    try:
        config_dict = _load_gui_config()
    except Exception:
        config_dict = {}
    window = DataFusionGUI(config_dict)
    window.show()
    app.exec()


if __name__ == "__main__":
    gui_runner_cli()
