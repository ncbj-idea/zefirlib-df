import json
import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

from datafusion.configs.address_config import AddressConfig
from datafusion.configs.bdot_config import BDOTConfig
from datafusion.configs.borders_config import BordersConfig
from datafusion.configs.ceeb_config import CEEBConfig
from datafusion.configs.global_config import GlobalConfig
from datafusion.configs.kiut_config import KIUTConfig
from datafusion.configs.merge_config import MergeConfig
from datafusion.configs.postprocessing_config import PostprocessingConfig
from datafusion.configs.pvgis_config import PVGISConfig

_logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


_ALLOWED_EXTENSION = [".json", ".yml", ".yaml"]


# Global variable to store the current config directory for include resolution
_current_config_dir = None


def include_constructor(loader, node):
    """Custom YAML constructor for !include directive."""
    global _current_config_dir
    filename = loader.construct_scalar(node)

    # Resolve the path relative to the current config directory
    if _current_config_dir is None:
        raise ConfigError("Config directory not set for include resolution")

    include_path = _current_config_dir / filename

    if not include_path.exists():
        raise ConfigError(f"Included file not found: {include_path}")

    # Save the current directory and set it to the included file's directory
    old_dir = _current_config_dir
    _current_config_dir = include_path.parent

    try:
        with open(include_path) as f:
            return yaml.safe_load(f)
    finally:
        # Restore the previous directory
        _current_config_dir = old_dir


# Register the !include constructor
yaml.SafeLoader.add_constructor("!include", include_constructor)


class Config(BaseModel):
    global_config: GlobalConfig
    bdot: BDOTConfig
    kiut: KIUTConfig
    borders: BordersConfig
    ceeb: CEEBConfig
    address: AddressConfig
    pvgis: PVGISConfig
    merge_config: MergeConfig
    postprocessing: PostprocessingConfig

    @classmethod
    def from_file(cls, path: Path):
        config = None
        if not path.exists() or path.suffix not in _ALLOWED_EXTENSION:
            raise ConfigError(f"File: {path} does not exist or it is not in expected extensions: {_ALLOWED_EXTENSION}")
        if path.suffix == ".json":
            config = cls.from_json(path)
        elif path.suffix in [".yml", ".yaml"]:
            config = cls.from_yml(path)
        return config

    @classmethod
    def from_yml(cls, yml_path: Path):
        global _current_config_dir
        try:
            # Set the current config directory for include resolution
            _current_config_dir = yml_path.parent

            with open(yml_path) as f:
                config = yaml.safe_load(f)

                # Extract global config
                global_config_data = config.pop("global", {})
                global_config = GlobalConfig(**global_config_data)

                cls._inject_global_config(config, global_config)

                return Config(**config)
        except yaml.YAMLError as e:
            _logger.error("Error parsing YML file: %s %s", yml_path, e)
        finally:
            # Reset the current config directory
            _current_config_dir = None

    @classmethod
    def from_dict(cls, config_dict: dict, validate_files: bool = True):
        config = dict(config_dict)

        global_config_data = config.pop("global", {})
        global_config = GlobalConfig(**global_config_data)

        cls._inject_global_config(config, global_config)

        if not validate_files and "ceeb" in config and config["ceeb"]:
            config["ceeb"]["skip_file_validation"] = True

        return Config(**config)

    @classmethod
    def from_json(cls, json_path: Path):
        global _current_config_dir
        try:
            # Set the current config directory for include resolution
            _current_config_dir = json_path.parent

            with open(json_path) as f:
                config = json.load(f)

                # Extract global config
                global_config_data = config.pop("global", {})
                global_config = GlobalConfig(**global_config_data)

                cls._inject_global_config(config, global_config)

                return Config(**config)
        except json.JSONDecodeError as e:
            _logger.error("Error parsing JSON file: %s %s", json_path, e)
        finally:
            # Reset the current config directory
            _current_config_dir = None

    @classmethod
    def _inject_global_config(cls, config: dict, global_config: GlobalConfig) -> None:
        """Inject global config values into sub-configs that need them.

        Args:
            config: The configuration dictionary to update.
            global_config: The GlobalConfig object containing global values.
        """
        terc = global_config.terc
        output_folder = global_config.output_folder
        input_folder = global_config.input_folder

        # Update configs that use TERC
        if "bdot" in config:
            config["bdot"]["terc"] = terc
        if "kiut" in config:
            config["kiut"]["terc"] = terc
        if "ceeb" in config:
            config["ceeb"]["terc"] = terc
        if "address" in config:
            config["address"]["terc"] = terc
        if "borders" in config:
            config["borders"]["terc"] = terc
        if "merge_config" in config:
            config["merge_config"]["terc"] = terc
            config["merge_config"]["output_path"] = output_folder
        if "postprocessing" in config:
            config["postprocessing"]["terc"] = terc
            config["postprocessing"]["output_path"] = output_folder
            config["postprocessing"]["input_path"] = input_folder

        # Add global_config back to the config dict
        config["global_config"] = global_config
