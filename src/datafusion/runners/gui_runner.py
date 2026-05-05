import logging
import os
import re
import sys
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Final

import yaml
from PySide6.QtCore import QLocale, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
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


class _LogSignalHandler(logging.Handler):
    """Forward log records to the GUI log signal."""

    def __init__(self, emit_fn: Callable[[str], None]) -> None:
        super().__init__(level=logging.INFO)
        self._emit_fn = emit_fn
        self.setFormatter(logging.Formatter("%(asctime)s: %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._emit_fn(self.format(record))
        except Exception:
            self.handleError(record)


class _SignalStream:
    """Redirect stdout/stderr writes to the GUI log signal."""

    def __init__(self, emit_fn: Callable[[str], None]) -> None:
        self._emit_fn = emit_fn
        self._buffer = ""

    def write(self, message: str) -> int:
        if not message:
            return 0

        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self._emit_fn(line)
        return len(message)

    def flush(self) -> None:
        if self._buffer:
            self._emit_fn(self._buffer)
            self._buffer = ""

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self) -> str:
        return sys.getdefaultencoding()


def _resolve_configs_dir() -> Path:
    """Resolve configs directory for local and Docker runs."""
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


def _read_yaml(path: Path) -> dict:
    """Read a single YAML file and return its contents as a dict."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file_handle:
        return yaml.safe_load(file_handle) or {}


def _load_full_config() -> dict:
    """Load config.yml with all !include directives resolved."""
    import datafusion.configs.config as config_module

    saved = config_module._current_config_dir
    config_module._current_config_dir = CONFIG_FILE.parent
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as file_handle:
            return yaml.safe_load(file_handle) or {}
    finally:
        config_module._current_config_dir = saved


def _load_gui_config() -> dict:
    """Load GUI-relevant config from individual YAML files."""
    return {
        "global": _read_yaml(GLOBAL_CONFIG),
        "ceeb": _read_yaml(CEEB_CONFIG),
    }


def _build_runtime_config(config_dict: dict) -> Config:
    """Create Config object from the full config with GUI overrides applied."""
    full_config = _load_full_config()
    for key in ("global", "ceeb"):
        if key in config_dict and config_dict[key]:
            full_config.setdefault(key, {}).update(config_dict[key])
    return Config.from_dict(full_config, validate_files=False)


class PipelineWorker(QThread):
    """Worker thread for running the pipeline to avoid blocking GUI."""

    log_signal = Signal(str)
    finished_signal = Signal(bool, str)
    paused_signal = Signal(str)

    def __init__(self, config_dict: dict):
        super().__init__()
        self.config_dict = dict(config_dict)

    def _create_config(self) -> Config:
        """Create Config object by loading the full config and applying GUI overrides."""
        return _build_runtime_config(self.config_dict)

    def _run_with_console_streaming(self, func: Callable[[], bool]) -> bool:
        """Run pipeline while forwarding logs and console output to the GUI."""
        root_logger = logging.getLogger()
        datafusion_logger = logging.getLogger("datafusion")
        log_handler = _LogSignalHandler(self.log_signal.emit)
        stdout_stream = _SignalStream(self.log_signal.emit)
        stderr_stream = _SignalStream(self.log_signal.emit)
        root_logger.addHandler(log_handler)
        datafusion_logger.addHandler(log_handler)
        try:
            with redirect_stdout(stdout_stream), redirect_stderr(stderr_stream):
                return func()
        finally:
            stdout_stream.flush()
            stderr_stream.flush()
            datafusion_logger.removeHandler(log_handler)
            root_logger.removeHandler(log_handler)

    def run(self) -> None:
        """Run the pipeline in a separate thread."""
        try:
            terc_for_log = (self.config_dict.get("global", {}) or {}).get("terc")
            _logger.info("Starting datafusion pipeline with TERC code: %s", terc_for_log)
            self.log_signal.emit("Processing started...")

            config = self._create_config()
            self.log_signal.emit("Config created in-memory")

            if self.isInterruptionRequested():
                self.log_signal.emit("Pipeline interrupted before execution.")
                self.finished_signal.emit(False, "Pipeline interrupted.")
                return

            completed = self._run_with_console_streaming(lambda: run_all(config, gui_mode=True))

            if self.isInterruptionRequested():
                self.log_signal.emit("Pipeline interrupted after execution.")
                self.finished_signal.emit(False, "Pipeline interrupted.")
                return

            if not completed:
                input_dir = (
                    config.postprocessing.input_path / config.global_config.terc / "postprocessing" / "inventory_files"
                )
                self.log_signal.emit(f"Postprocessing paused. Place data files in:\n  {input_dir}")
                self.paused_signal.emit(str(input_dir))
                return

            message = f"Pipeline completed successfully for TERC: {terc_for_log}"
            self.log_signal.emit(message)
            self.finished_signal.emit(True, message)

        except Exception as exc:
            error_msg = f"Error running pipeline: {exc}"
            _logger.error(error_msg)
            _logger.exception(exc)
            self.log_signal.emit(error_msg)
            self.finished_signal.emit(False, error_msg)


class DataFusionGUI(QMainWindow):
    """Main GUI window for DataFusion Pipeline."""

    def __init__(self, config_dict: dict):
        super().__init__()
        self.worker: PipelineWorker | None = None
        self.config_dict = dict(config_dict)
        self.init_ui()
        self._check_paused_state()

    def init_ui(self) -> None:
        """Initialize the user interface."""
        self.setWindowTitle("DataFusion")
        self.setGeometry(100, 100, 650, 800)
        self.center_on_screen()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        def add_section_header(text: str) -> None:
            container = QWidget()
            header_layout = QHBoxLayout(container)
            header_layout.setContentsMargins(0, 12, 0, 8)
            header_layout.setSpacing(12)
            label = QLabel(text)
            label.setFont(QFont("Arial", 14, QFont.Bold))
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            line.setStyleSheet("background-color: #dee2e6;")
            line.setFixedHeight(1)
            header_layout.addWidget(label)
            header_layout.addWidget(line, 1)
            layout.addWidget(container)

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

        input_layout = QHBoxLayout()
        terc_label = QLabel("Kod TERC")
        terc_label.setFixedWidth(200)
        self.terc_input = QLineEdit()
        self.terc_input.setPlaceholderText("Podaj 7-cyfrowy identyfikator")
        self.terc_input.setAccessibleName("Kod TERC")
        self.terc_input.setAccessibleDescription("Identyfikator jednostki samorządu terytorialnego")
        terc_label.setBuddy(self.terc_input)

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
        self.ceeb_devices_path_input.setAccessibleName("Ścieżka do pliku urządzeń CEEB")

        ceeb_class_initial = (self.config_dict.get("ceeb") or {}).get("ceeb_class_file_path")
        self.ceeb_classes_path_input, self.ceeb_classes_pick_button = self._add_path_row(
            layout,
            "Klasy",
            "Wybierz plik .csv/.xlsx/.xls…",
            initial_value=ceeb_class_initial,
            pick_fn=self.pick_file,
        )
        self.ceeb_classes_path_input.setAccessibleName("Ścieżka do pliku klas CEEB")

        layout.addSpacing(6)

        self.pause_info_label = QLabel("")
        self.pause_info_label.setWordWrap(True)
        self.pause_info_label.setStyleSheet("color: #d63384; font-weight: bold; padding: 8px;")
        self.pause_info_label.setAccessibleName("Informacja o wstrzymanym postprocessingu")
        self.pause_info_label.hide()
        layout.addWidget(self.pause_info_label)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: blue;")
        self.status_label.setFixedHeight(24)
        layout.addWidget(self.status_label)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("terminal")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(300)
        self.log_view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.log_view.setFocusPolicy(Qt.NoFocus)
        self.log_view.setAccessibleName("Panel logów")
        self.log_view.setAccessibleDescription("Wyświetla postęp i wyniki przetwarzania")
        layout.addWidget(self.log_view)

        button_layout = QHBoxLayout()

        self.run_button = QPushButton("Pobierz dane")
        self.run_button.setFixedWidth(140)
        self.run_button.clicked.connect(self.run_pipeline)
        self.run_button.setObjectName("primaryButton")
        self.run_button.setAccessibleName("Pobierz dane")
        self.run_button.setAutoDefault(True)
        self.run_button.setFocusPolicy(Qt.StrongFocus)

        self.exit_button = QPushButton("Zamknij")
        self.exit_button.setFixedWidth(90)
        self.exit_button.clicked.connect(self.close)
        self.exit_button.setObjectName("secondaryContainedButton")
        self.exit_button.setAccessibleName("Zamknij aplikację")
        self.exit_button.setAutoDefault(True)
        self.exit_button.setFocusPolicy(Qt.StrongFocus)

        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.exit_button)
        button_layout.setContentsMargins(0, 12, 0, 12)
        layout.addLayout(button_layout)

        pause_button_layout = QHBoxLayout()

        self.resume_button = QPushButton("Wznów")
        self.resume_button.setFixedWidth(140)
        self.resume_button.setObjectName("primaryButton")
        self.resume_button.setAccessibleName("Wznów przetwarzanie")
        self.resume_button.setAutoDefault(True)
        self.resume_button.setFocusPolicy(Qt.StrongFocus)
        self.resume_button.clicked.connect(self._resume_postprocessing)
        self.resume_button.hide()

        self.pause_quit_button = QPushButton("Zamknij i wznów później")
        self.pause_quit_button.setFixedWidth(200)
        self.pause_quit_button.setObjectName("secondaryContainedButton")
        self.pause_quit_button.setAccessibleName("Zamknij i wznów później")
        self.pause_quit_button.setAutoDefault(True)
        self.pause_quit_button.setFocusPolicy(Qt.StrongFocus)
        self.pause_quit_button.clicked.connect(self._on_pause_quit)
        self.pause_quit_button.hide()

        pause_button_layout.addWidget(self.resume_button)
        pause_button_layout.addWidget(self.pause_quit_button)
        pause_button_layout.setContentsMargins(0, 4, 0, 12)
        layout.addLayout(pause_button_layout)

        QWidget.setTabOrder(self.terc_input, self.ceeb_devices_path_input)
        QWidget.setTabOrder(self.ceeb_devices_path_input, self.ceeb_devices_pick_button)
        QWidget.setTabOrder(self.ceeb_devices_pick_button, self.ceeb_classes_path_input)
        QWidget.setTabOrder(self.ceeb_classes_path_input, self.ceeb_classes_pick_button)
        QWidget.setTabOrder(self.ceeb_classes_pick_button, self.run_button)
        QWidget.setTabOrder(self.run_button, self.exit_button)
        QWidget.setTabOrder(self.exit_button, self.resume_button)
        QWidget.setTabOrder(self.resume_button, self.pause_quit_button)

        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)

        self.terc_input.setFocus()
        self._apply_stylesheet()

    def run_pipeline(self) -> None:
        """Run the pipeline with the entered TERC code."""
        terc_code = self.terc_input.text().strip()

        if not terc_code:
            self._show_error("Podaj kod TERC", self.terc_input)
            return

        if not re.fullmatch(r"\d{7}", terc_code):
            self._show_error("Kod TERC musi składać się z dokładnie 7 cyfr", self.terc_input)
            return

        ceeb_devices_path = self._validate_file_path(
            self.ceeb_devices_path_input.text(),
            "CEEB Urządzenia",
            self.ceeb_devices_path_input,
        )
        if ceeb_devices_path is None:
            return

        ceeb_classes_path = self._validate_file_path(
            self.ceeb_classes_path_input.text(),
            "CEEB Klasy",
            self.ceeb_classes_path_input,
        )
        if ceeb_classes_path is None:
            return

        self.log_view.clear()
        self._hide_pause_ui()
        self._show_status("Uruchomiono proces...")
        self.run_button.setEnabled(False)

        self.config_dict.setdefault("global", {})["terc"] = terc_code
        self.config_dict.setdefault("ceeb", {})["ceeb_devices_file_path"] = ceeb_devices_path
        self.config_dict.setdefault("ceeb", {})["ceeb_class_file_path"] = ceeb_classes_path

        self.worker = PipelineWorker(self.config_dict)
        self.worker.log_signal.connect(self._append_log)
        self.worker.finished_signal.connect(self._on_pipeline_finished)
        self.worker.paused_signal.connect(self._on_pipeline_paused)
        self.worker.start()

    def _append_log(self, message: str) -> None:
        """Append message to terminal log view."""
        self.log_view.appendPlainText(message)
        self.log_view.ensureCursorVisible()

    def _on_pipeline_finished(self, success: bool, message: str) -> None:
        """Handle pipeline completion."""
        self.run_button.setEnabled(True)
        self._hide_pause_ui()
        if success:
            self._show_status("Proces zakończony sukcesem")
        else:
            self._show_error(f"Proces zakończony błędem: {message}")

    def _on_pipeline_paused(self, input_dir: str) -> None:
        """Handle pipeline pause."""
        self.run_button.setEnabled(False)
        self.pause_info_label.setText(
            f"Postprocessing wstrzymany.\nUmieść pliki inwentaryzacji w folderze:\n  {input_dir}"
        )
        self.pause_info_label.show()
        self.resume_button.show()
        self.pause_quit_button.show()
        self.exit_button.hide()
        self._show_status("Oczekiwanie na pliki...")

    def _resume_postprocessing(self) -> None:
        """Resume postprocessing after user placed files."""
        self._hide_pause_ui()
        self.log_view.clear()
        self._show_status("Wznawianie przetwarzania...")
        self.run_pipeline()

    def _on_pause_quit(self) -> None:
        """User chose to close the app and resume later."""
        self.run_button.setEnabled(True)
        self._hide_pause_ui()
        self._show_status("Zatrzymano. Uruchom ponownie, aby wznowić.")
        self.close()

    def _hide_pause_ui(self) -> None:
        """Hide pause/resume UI elements."""
        self.pause_info_label.hide()
        self.resume_button.hide()
        self.pause_quit_button.hide()
        self.exit_button.show()

    def _check_paused_state(self) -> None:
        """On startup, check if postprocessing was paused and show resume prompt."""
        terc_code = self.terc_input.text().strip()
        if not terc_code:
            return

        try:
            from datafusion.database.session import get_engine
            from datafusion.runners.postprocessing_runner import is_postprocessing_paused

            config = _build_runtime_config(self.config_dict)
            engine = get_engine()
            if is_postprocessing_paused(terc_code, engine):
                input_dir = config.postprocessing.input_path / terc_code / "postprocessing" / "inventory_files"
                self._on_pipeline_paused(str(input_dir))
                self._append_log("Wykryto wstrzymany postprocessing. Możesz wznowić przetwarzanie.\n")
        except Exception as exc:
            _logger.debug("Could not check paused state: %s", exc)

    def _apply_stylesheet(self) -> None:
        """Load QSS from file, resolve CSS variable references, and apply."""
        try:
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
                _logger.debug("Stylesheet not found in any of: %s", possible_paths)
                return

            content = style_path.read_text(encoding="utf-8")
            var_pattern = re.compile(r"--([a-zA-Z0-9_-]+)\s*:\s*([^;]+);")
            variables = {match.group(1): match.group(2).strip() for match in var_pattern.finditer(content)}

            def repl_var(match: re.Match[str]) -> str:
                name = match.group(1)
                return variables.get(name, match.group(0))

            content_resolved = re.sub(r"var\(--([a-zA-Z0-9_-]+)\)", repl_var, content)
            content_resolved = re.sub(r":root\s*\{.*?\}", "", content_resolved, flags=re.DOTALL)
            self.setStyleSheet(content_resolved)
        except Exception as exc:
            _logger.warning("Failed to apply stylesheet: %s", exc)

    def center_on_screen(self) -> None:
        """Move the window to the center of the primary screen."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        x = geom.center().x() - self.width() // 2
        y = geom.center().y() - self.height() // 2
        self.move(x, y)

    def closeEvent(self, event) -> None:  # noqa: N802
        """Handle window close event."""
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            if not self.worker.wait(3000):
                _logger.warning("Worker did not stop in time, terminating")
                self.worker.terminate()
                self.worker.wait(1000)
        event.accept()

    def _show_error(self, message: str, focus_widget: QWidget | None = None) -> None:
        """Display an error message in the status label."""
        self.status_label.setText(f"✖ Błąd: {message}")
        self.status_label.setStyleSheet("color: #c92a2a; font-weight: bold;")
        if focus_widget is not None:
            QTimer.singleShot(0, focus_widget.setFocus)

    def _show_status(self, message: str) -> None:
        """Display a success/info message in the status label."""
        self.status_label.setText(f"✔ {message}")
        self.status_label.setStyleSheet("color: #2b8a3e; font-weight: bold;")

    def _add_path_row(
        self,
        layout: QVBoxLayout,
        label_text: str,
        placeholder: str,
        initial_value: str | None = None,
        pick_fn: Callable[[QLineEdit], None] | None = None,
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
        label.setBuddy(line_edit)
        button = QPushButton("Wybierz")
        button.setObjectName("primaryOutlinedButton")
        button.setFixedHeight(28)
        button.setAutoDefault(True)
        button.setAccessibleName(f"Wybierz {label_text}")
        button.setFocusPolicy(Qt.StrongFocus)
        if pick_fn:
            button.clicked.connect(lambda: pick_fn(line_edit))
        row.addWidget(label)
        row.addWidget(line_edit)
        row.addWidget(button)
        layout.addLayout(row)
        return line_edit, button

    _ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

    def _validate_file_path(self, raw_path: str, field_name: str, focus_widget: QWidget | None = None) -> str | None:
        """Validate a file path input. Returns cleaned path or None on error."""
        path_str = raw_path.strip()
        if not path_str:
            self._show_error(f"Podaj ścieżkę do pliku {field_name}", focus_widget)
            return None
        path = Path(path_str)
        if not path.is_file() or path.suffix.lower() not in self._ALLOWED_EXTENSIONS:
            self._show_error(
                f"Nieprawidłowa ścieżka do pliku {field_name}. Plik nie istnieje lub ma nieobsługiwany format",
                focus_widget,
            )
            return None
        return path_str

    def pick_file(self, target_input: QLineEdit) -> None:
        """Open file picker and populate the target input."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik CSV/Excel",
            str(Path.cwd()),
            "Pliki CSV/Excel (*.csv *.xlsx *.xls);;Wszystkie pliki (*)",
        )
        if filename:
            target_input.setText(filename)


def gui_runner_cli() -> None:
    """CLI entry point for the GUI runner."""
    app = QApplication([])
    QLocale.setDefault(QLocale(QLocale.Polish, QLocale.Poland))
    try:
        config_dict = _load_gui_config()
    except Exception:
        config_dict = {}
    window = DataFusionGUI(config_dict)
    window.show()
    app.exec()


if __name__ == "__main__":
    gui_runner_cli()
