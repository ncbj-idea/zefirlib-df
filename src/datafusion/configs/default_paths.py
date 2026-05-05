import os
from pathlib import Path


def get_airflow_config_absolute_path() -> Path:
    project_path = os.getenv("DATAFUSION_HOME")
    return Path(project_path) / "datafusion_input" / "configs"
