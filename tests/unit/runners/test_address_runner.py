from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from datafusion.runners import address_runner as runner_module


@pytest.mark.parametrize("with_borders", [True, False])
def test_runner_passes_border_configuration_to_reader(monkeypatch: pytest.MonkeyPatch, with_borders: bool) -> None:
    reader = Mock()
    monkeypatch.setattr(runner_module, "AddressReader", reader)
    config, engine, settings = Mock(), Mock(), Mock()
    borders = Mock() if with_borders else None
    kwargs = {"borders_config": borders} if with_borders else {}

    runner_module.AddressRunner(config, engine, settings, **kwargs).run()

    reader.assert_called_once_with(config=config, db_engine=engine, db_settings=settings, borders_config=borders)
    reader.return_value.run.assert_called_once_with()


def test_address_runner_supplies_global_border_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Mock()
    engine, settings = Mock(), Mock()
    config = SimpleNamespace(address=Mock(), borders=Mock())
    monkeypatch.setattr(runner_module, "AddressRunner", runner)
    monkeypatch.setattr(runner_module, "get_engine", lambda: engine)
    monkeypatch.setattr(runner_module, "DBSettings", lambda: settings)

    runner_module.address_runner(config)

    runner.assert_called_once_with(
        config=config.address, engine=engine, db_settings=settings, borders_config=config.borders
    )
    runner.return_value.run.assert_called_once_with()
