import logging
import logging.config
import os

import yaml


def setup_logging(
    config_path: str = "logging.yaml",
    default_level: int = logging.INFO,
    env_key: str = "LOG_CFG",
) -> None:
    """Setup logging configuration"""
    path = config_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path) as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)
