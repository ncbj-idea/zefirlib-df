from importlib.resources import files
from pathlib import Path


def get_resource_path(filename: str) -> Path:
    """Get the path to a resource file in the datafusion.resources package.

    This function works regardless of whether the package is installed
    in editable mode or as a regular package in site-packages.

    Args:
        filename: Name of the resource file (e.g., 'building_parameters.xlsx')

    Returns:
        Path to the resource file.
    """
    return Path(files("datafusion.resources").joinpath(filename))


ROOT_DIR = Path(__file__).parent.parent
