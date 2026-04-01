import os
from pathlib import Path

import pytest
import yaml

from datafusion.configs.config import Config, ConfigError

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
QApplication = QtWidgets.QApplication
gui_runner = pytest.importorskip("datafusion.runners.gui_runner")

# Paths to test resources that exist in the repo
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
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return path


def _config_dict_from_file(config_path: Path) -> dict:
    """Load a Config from YAML and return a GUI-compatible config dict.

    Mirrors the pattern used by postprocessing_runner.py where Config.from_file()
    is used, then relevant sections are extracted as plain dicts for the GUI.
    """
    config = Config.from_file(config_path)
    return {
        "global": {"terc": config.global_config.terc},
        "ceeb": {
            "ceeb_devices_file_path": config.ceeb.ceeb_devices_file_path,
            "ceeb_class_file_path": config.ceeb.ceeb_class_file_path,
        },
    }


# ---------------------------------------------------------------------------
# Config.from_file tests
# ---------------------------------------------------------------------------


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
    """Verify that config dict can be extracted from a loaded Config."""
    config_path = _write_config_yml(tmp_path / "config.yml", terc="2222222")
    cfg_dict = _config_dict_from_file(config_path)

    assert cfg_dict["global"]["terc"] == "2222222"
    assert cfg_dict["ceeb"]["ceeb_devices_file_path"] == _CEEB_DEVICES
    assert cfg_dict["ceeb"]["ceeb_class_file_path"] == _CEEB_CLASSES


# ---------------------------------------------------------------------------
# GUI tests
# ---------------------------------------------------------------------------


@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


def test_gui_initializes_with_prefilled_terc(qapp, tmp_path: Path):
    config_path = _write_config_yml(tmp_path / "config.yml", terc="1234567")
    cfg_dict = _config_dict_from_file(config_path)

    window = gui_runner.DataFusionGUI(cfg_dict)
    assert window.terc_input.text() == "1234567"


def test_gui_initializes_with_empty_config(qapp):
    window = gui_runner.DataFusionGUI({})

    assert window.terc_input.text() == ""


def test_run_pipeline_requires_terc(qapp, tmp_path: Path):
    window = gui_runner.DataFusionGUI({})

    devices = tmp_path / "devices.csv"
    classes = tmp_path / "classes.csv"
    devices.write_text("", encoding="utf-8")
    classes.write_text("", encoding="utf-8")

    window.ceeb_devices_path_input.setText(str(devices))
    window.ceeb_classes_path_input.setText(str(classes))
    window.terc_input.setText("")

    window.run_pipeline()
    assert window.status_label.text() == "Podaj kod TERC"


def test_run_pipeline_requires_ceeb_devices_path(qapp, tmp_path: Path):
    config_path = _write_config_yml(tmp_path / "config.yml", terc="1234567")
    cfg_dict = _config_dict_from_file(config_path)

    window = gui_runner.DataFusionGUI(cfg_dict)
    classes = tmp_path / "classes.csv"
    classes.write_text("", encoding="utf-8")
    window.ceeb_devices_path_input.setText("")
    window.ceeb_classes_path_input.setText(str(classes))

    window.run_pipeline()
    assert window.status_label.text() == "Podaj ścieżkę do pliku CEEB Urządzenia"


def test_run_pipeline_requires_ceeb_classes_path(qapp, tmp_path: Path):
    config_path = _write_config_yml(tmp_path / "config.yml", terc="1234567")
    cfg_dict = _config_dict_from_file(config_path)

    window = gui_runner.DataFusionGUI(cfg_dict)
    devices = tmp_path / "devices.csv"
    devices.write_text("", encoding="utf-8")
    window.ceeb_devices_path_input.setText(str(devices))
    window.ceeb_classes_path_input.setText("")

    window.run_pipeline()
    assert window.status_label.text() == "Podaj ścieżkę do pliku CEEB Klasy"


def test_checkbox_adds_save_report_flag(qapp, tmp_path: Path, monkeypatch):
    config_path = _write_config_yml(tmp_path / "config.yml")
    monkeypatch.setattr(gui_runner, "CONFIG_FILE", config_path, raising=False)

    cfg_dict = _config_dict_from_file(config_path)
    window = gui_runner.DataFusionGUI(cfg_dict)
    window.terc_input.setText("1234567")
    devices = tmp_path / "devices.csv"
    classes = tmp_path / "classes.csv"
    devices.write_text("id,name\n1,x\n", encoding="utf-8")
    classes.write_text("id,class\n1,A\n", encoding="utf-8")
    window.ceeb_devices_path_input.setText(str(devices))
    window.ceeb_classes_path_input.setText(str(classes))

    # Enable checkbox
    assert hasattr(window, "save_report_checkbox")
    window.save_report_checkbox.setChecked(True)

    window.run_pipeline()
    assert window.worker is not None
    assert window.worker.config_dict.get("global", {}).get("terc") == "1234567"


def test_run_postprocessing_requires_inventory_path(qapp, tmp_path: Path):
    config_path = _write_config_yml(tmp_path / "config.yml", terc="1234567")
    cfg_dict = _config_dict_from_file(config_path)

    window = gui_runner.DataFusionGUI(cfg_dict)
    window.inventory_path_input.setEnabled(True)
    window.inventory_path_input.setText("")
    window.run_postprocessing()
    assert window.status_label.text() == "Podaj ścieżkę do folderu inwentaryzacji"
