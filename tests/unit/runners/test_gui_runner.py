import logging
import os
import sys
from pathlib import Path

import pytest
import yaml

from datafusion.configs.config import Config, ConfigError
from datafusion.database import session as session_module
from datafusion.runners import postprocessing_runner

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
QApplication = QtWidgets.QApplication
gui_runner = pytest.importorskip("datafusion.runners.gui_runner")

_KIUT_TERC_XML = str(Path("tests/resources/kiut/TERC_Urzedowy.xml"))
_CEEB_DEVICES = str(Path("tests/resources/ceeb/ceeb_devices.csv"))
_CEEB_CLASSES = str(Path("tests/resources/ceeb/ceeb_classes.csv"))


def _minimal_config_dict(terc: str = "1863011") -> dict:
    """Return a minimal but valid raw config dict for Config(**config)."""
    return {
        "global": {
            "terc": terc,
        },
        "bdot": {
            "terc": terc,
            "tmp_table_name": "bdot",
            "tmp_table_schema": "tmp",
            "geom_col_name": "geometria",
            "source_column_map": None,
        },
        "kiut": {
            "terc_urzedowy_xml_path": _KIUT_TERC_XML,
            "terc": terc,
            "layers": ["przewod_cieplowniczy"],
            "polygonization": {
                "method": "ANALYZE_COLORS_ON_MAP",
                "grid_existence_threshold": 0.005,
            },
            "wms": {},
            "number_of_slices_of_image_side": 50,
        },
        "borders": {
            "url": "https://mapy.geoportal.gov.pl/wss/service/PZGIK/PRG/WFS/AdministrativeBoundaries",
            "layer_name": "A05_Granice_jednostek_ewidencyjnych",
            "tmp_table_name": "tmp_administrative_boundaries",
            "wfs_version": "1.1.0",
            "timeout": 600,
            "tmp_table_schema": "tmp",
        },
        "ceeb": {
            "terc": terc,
            "ceeb_devices_file_path": _CEEB_DEVICES,
            "ceeb_class_file_path": _CEEB_CLASSES,
            "tmp_table_schema": "tmp",
        },
        "address": {
            "terc": terc,
            "url": "https://opendata.geoportal.gov.pl/prg/adresy/",
            "layer_name": "PRG_PunktAdresowy",
            "tmp_table_name": "tmp_address_point",
            "tmp_table_schema": "tmp",
            "geometry_column_name": "msgeometry",
        },
        "pvgis": {
            "lat": 52.403,
            "lon": 20.916,
            "peakpower": 1.0,
            "loss": 14,
        },
        "merge_config": {
            "terc": terc,
        },
        "postprocessing": {
            "terc": terc,
            "input_path": "output",
            "output_path": "output",
        },
    }


def _write_config_yml(path: Path, terc: str = "1863011") -> Path:
    """Write a minimal valid config YAML file and return its path."""
    data = _minimal_config_dict(terc)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        yaml.safe_dump(data, file_handle, allow_unicode=True, sort_keys=False)
    return path


def _config_dict_from_file(config_path: Path) -> dict:
    """Load a Config from YAML and return a GUI-compatible config dict."""
    config = Config.from_file(config_path)
    return {
        "global": {"terc": config.global_config.terc},
        "ceeb": {
            "ceeb_devices_file_path": config.ceeb.ceeb_devices_file_path,
            "ceeb_class_file_path": config.ceeb.ceeb_class_file_path,
        },
    }


class _DummySignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in self._callbacks:
            callback(*args)


class _DummyWorker:
    mode = "success"
    paused_path = "output/1234567/postprocessing/inventory_files"

    def __init__(self, config_dict: dict):
        self.config_dict = dict(config_dict)
        self.log_signal = _DummySignal()
        self.finished_signal = _DummySignal()
        self.paused_signal = _DummySignal()
        self._running = False

    def start(self) -> None:
        self._running = True
        if self.mode == "paused":
            self.paused_signal.emit(self.paused_path)
        elif self.mode == "error":
            self.finished_signal.emit(False, "boom")
        else:
            self.finished_signal.emit(True, "ok")
        self._running = False

    def isRunning(self) -> bool:  # noqa: N802
        return self._running

    def request_interruption(self) -> None:
        self._running = False

    requestInterruption = request_interruption  # noqa: N815

    def wait(self, _timeout: int) -> bool:
        return True

    def terminate(self) -> None:
        self._running = False


@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


@pytest.fixture
def gui_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    config_path = _write_config_yml(tmp_path / "config.yml", terc="1234567")
    monkeypatch.setattr(gui_runner, "CONFIG_FILE", config_path)
    return _config_dict_from_file(config_path)


def test_config_from_file_loads_yaml(tmp_path: Path) -> None:
    config_path = _write_config_yml(tmp_path / "config.yml", terc="9999999")
    config = Config.from_file(config_path)

    assert isinstance(config, Config)
    assert config.global_config.terc == "9999999"
    assert config.bdot.terc == "9999999"
    assert config.ceeb.ceeb_devices_file_path == _CEEB_DEVICES
    assert config.ceeb.ceeb_class_file_path == _CEEB_CLASSES
    assert config.postprocessing.terc == "9999999"


def test_config_from_file_raises_on_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.yml"
    with pytest.raises(ConfigError):
        Config.from_file(missing)


def test_config_from_file_raises_on_invalid_extension(tmp_path: Path) -> None:
    bad = tmp_path / "config.txt"
    bad.write_text("terc: '123'", encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.from_file(bad)


def test_config_dict_extraction(tmp_path: Path) -> None:
    config_path = _write_config_yml(tmp_path / "config.yml", terc="2222222")
    cfg_dict = _config_dict_from_file(config_path)

    assert cfg_dict["global"]["terc"] == "2222222"
    assert cfg_dict["ceeb"]["ceeb_devices_file_path"] == _CEEB_DEVICES
    assert cfg_dict["ceeb"]["ceeb_class_file_path"] == _CEEB_CLASSES


def test_gui_initializes_with_prefilled_terc(qapp, gui_config: dict) -> None:
    window = gui_runner.DataFusionGUI(gui_config)

    assert window.terc_input.text() == "1234567"


def test_gui_initializes_with_empty_config(qapp) -> None:
    window = gui_runner.DataFusionGUI({})

    assert window.terc_input.text() == ""


def test_run_pipeline_requires_terc(qapp, tmp_path: Path) -> None:
    window = gui_runner.DataFusionGUI({})

    devices = tmp_path / "devices.csv"
    classes = tmp_path / "classes.csv"
    devices.write_text("", encoding="utf-8")
    classes.write_text("", encoding="utf-8")

    window.ceeb_devices_path_input.setText(str(devices))
    window.ceeb_classes_path_input.setText(str(classes))
    window.terc_input.setText("")

    window.run_pipeline()

    assert window.status_label.text() == "✖ Błąd: Podaj kod TERC"


def test_run_pipeline_requires_exactly_seven_terc_digits(qapp, tmp_path: Path) -> None:
    window = gui_runner.DataFusionGUI({})

    devices = tmp_path / "devices.csv"
    classes = tmp_path / "classes.csv"
    devices.write_text("", encoding="utf-8")
    classes.write_text("", encoding="utf-8")

    window.ceeb_devices_path_input.setText(str(devices))
    window.ceeb_classes_path_input.setText(str(classes))
    window.terc_input.setText("123")

    window.run_pipeline()

    assert window.status_label.text() == "✖ Błąd: Kod TERC musi składać się z dokładnie 7 cyfr"


def test_run_pipeline_requires_ceeb_devices_path(qapp, gui_config: dict, tmp_path: Path) -> None:
    window = gui_runner.DataFusionGUI(gui_config)
    classes = tmp_path / "classes.csv"
    classes.write_text("", encoding="utf-8")
    window.ceeb_devices_path_input.setText("")
    window.ceeb_classes_path_input.setText(str(classes))

    window.run_pipeline()

    assert window.status_label.text() == "✖ Błąd: Podaj ścieżkę do pliku CEEB Urządzenia"


def test_run_pipeline_requires_ceeb_classes_path(qapp, gui_config: dict, tmp_path: Path) -> None:
    window = gui_runner.DataFusionGUI(gui_config)
    devices = tmp_path / "devices.csv"
    devices.write_text("", encoding="utf-8")
    window.ceeb_devices_path_input.setText(str(devices))
    window.ceeb_classes_path_input.setText("")

    window.run_pipeline()

    assert window.status_label.text() == "✖ Błąd: Podaj ścieżkę do pliku CEEB Klasy"


def test_run_pipeline_shows_pause_ui_when_postprocessing_pauses(
    qapp,
    gui_config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gui_runner, "PipelineWorker", _DummyWorker)
    _DummyWorker.mode = "paused"
    _DummyWorker.paused_path = "output/1234567/postprocessing/inventory_files"

    window = gui_runner.DataFusionGUI(gui_config)
    window.terc_input.setText("1234567")

    window.run_pipeline()

    assert not window.run_button.isEnabled()
    assert not window.pause_info_label.isHidden()
    assert not window.resume_button.isHidden()
    assert not window.pause_quit_button.isHidden()
    assert "output/1234567/postprocessing/inventory_files" in window.pause_info_label.text()
    assert window.status_label.text() == "✔ Oczekiwanie na pliki..."


def test_resume_button_reruns_pipeline(qapp, gui_config: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    called = []

    monkeypatch.setattr(gui_runner.DataFusionGUI, "run_pipeline", lambda self: called.append(self.terc_input.text()))

    window = gui_runner.DataFusionGUI(gui_config)
    window.terc_input.setText("1234567")
    window._on_pipeline_paused("output/1234567/postprocessing/inventory_files")

    window._resume_postprocessing()

    assert called == ["1234567"]
    assert window.status_label.text() == "✔ Wznawianie przetwarzania..."


def test_pause_quit_hides_pause_ui(qapp, gui_config: dict) -> None:
    window = gui_runner.DataFusionGUI(gui_config)
    window._on_pipeline_paused("output/1234567/postprocessing/inventory_files")

    window._on_pause_quit()

    assert window.run_button.isEnabled()
    assert window.pause_info_label.isHidden()
    assert window.resume_button.isHidden()
    assert window.pause_quit_button.isHidden()
    assert window.status_label.text() == "✔ Zatrzymano. Uruchom ponownie, aby wznowić."


def test_startup_detects_paused_postprocessing(
    qapp,
    gui_config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_module, "get_engine", lambda: object())
    monkeypatch.setattr(postprocessing_runner, "is_postprocessing_paused", lambda terc, engine: terc == "1234567")

    window = gui_runner.DataFusionGUI(gui_config)

    assert not window.pause_info_label.isHidden()
    assert not window.resume_button.isHidden()
    assert "Wykryto wstrzymany postprocessing" in window.log_view.toPlainText()


def test_pipeline_worker_streams_logs_and_console_output(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = gui_runner.PipelineWorker({"global": {"terc": "1234567"}})
    messages = []
    worker.log_signal.connect(messages.append)

    monkeypatch.setattr(worker, "_create_config", lambda: object())

    def _fake_run_all(_config, gui_mode: bool = False) -> bool:
        assert gui_mode is True
        logging.getLogger("datafusion.tests.gui").info("Pipeline step from logger")
        print("stdout message")
        print("stderr message", file=sys.stderr)
        return True

    monkeypatch.setattr(gui_runner, "run_all", _fake_run_all)

    worker.run()

    assert any("Pipeline step from logger" in message for message in messages)
    assert "stdout message" in messages
    assert "stderr message" in messages
